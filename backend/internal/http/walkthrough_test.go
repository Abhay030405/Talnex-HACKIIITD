package http_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"mime/multipart"
	nethttp "net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	apihttp "github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/http"
)

func setupWalkthrough(t *testing.T, limits apihttp.WalkthroughLimits) (*httptest.Server, *fakeFiles) {
	t.Helper()
	files := &fakeFiles{saved: map[string][]byte{}}
	h := apihttp.NewHandler(apihttp.Options{
		Pool: dbtest.Pool(t), AuthSecret: secret, WebOrigin: "http://localhost:3000",
		Files: files, ProofLinks: viewLinks{}, Walkthrough: limits,
		Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
	})
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return srv, files
}

func postAudio(t *testing.T, url, email, role string, data []byte) (int, string) {
	t.Helper()
	var body bytes.Buffer
	mw := multipart.NewWriter(&body)
	part, _ := mw.CreateFormFile("audio", "q.webm")
	_, _ = part.Write(data)
	_ = mw.Close()
	req, _ := nethttp.NewRequest("POST", url, &body)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	tok, _ := auth.SignWithRole(secret, email, "", role, time.Minute)
	req.Header.Set("Authorization", "Bearer "+tok)
	resp, err := nethttp.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, string(out)
}

func walkProject(t *testing.T, srv *httptest.Server, email string) string {
	t.Helper()
	code, out := roleCall(t, srv.URL, "POST", "/v1/events", email, "organizer", eventBody())
	event := idOf(t, code, out)
	code, out = roleCall(t, srv.URL, "POST", "/v1/events/"+event+"/projects", email, "organizer",
		map[string]any{"team_name": "t", "live_url": "https://example.com"})
	return idOf(t, code, out)
}

func TestTypedQuestionQueuesAnAnswerJobAndEachQuestionIsItsOwnJob(t *testing.T) {
	srv, _ := setupWalkthrough(t, apihttp.WalkthroughLimits{AudioMaxBytes: 1 << 20, QuestionsPerDay: 10})
	email := "walk-" + uuid.NewString()[:8] + "@example.com"
	project := walkProject(t, srv, email)

	ids := map[string]bool{}
	for i := 0; i < 2; i++ {
		code, out := roleCall(t, srv.URL, "POST", "/v1/projects/"+project+"/walkthroughs", email, "organizer",
			map[string]any{"question": "Walk me through the chat"})
		if code != 202 {
			t.Fatalf("ask: %d %s", code, out)
		}
		var got struct{ ID, Status string }
		_ = json.Unmarshal([]byte(out), &got)
		if got.Status != "queued" || got.ID == "" {
			t.Fatalf("answer = %s", out)
		}
		ids[got.ID] = true
	}
	var jobs int
	if err := dbtest.Pool(t).QueryRow(context.Background(), `
		SELECT count(*) FROM jobs WHERE job_type = 'walkthrough_answer' AND runner = 'python' AND target_type = 'project'
		   AND target_id = $1::uuid AND pipeline IS NULL AND input->>'walkthrough_id' = ANY($2)`, project, keys(ids)).Scan(&jobs); err != nil {
		t.Fatal(err)
	}
	if jobs != 2 {
		t.Errorf("want 2 separate jobs, got %d", jobs)
	}

	code, out := roleCall(t, srv.URL, "GET", "/v1/projects/"+project+"/walkthroughs", email, "organizer", nil)
	var list []map[string]any
	_ = json.Unmarshal([]byte(out), &list)
	if code != 200 || len(list) != 2 {
		t.Errorf("list: %d %s", code, out)
	}
}

func keys(m map[string]bool) []string {
	out := []string{}
	for k := range m {
		out = append(out, k)
	}
	return out
}

func TestWalkthroughRules(t *testing.T) {
	srv, files := setupWalkthrough(t, apihttp.WalkthroughLimits{AudioMaxBytes: 100, QuestionsPerDay: 2})
	email := "walkr-" + uuid.NewString()[:8] + "@example.com"
	project := walkProject(t, srv, email)
	path := "/v1/projects/" + project + "/walkthroughs"

	if code, _ := roleCall(t, srv.URL, "POST", path, email, "organizer", map[string]any{"question": "  "}); code != 400 {
		t.Errorf("blank question: %d", code)
	}
	if code, _ := roleCall(t, srv.URL, "POST", path, email, "organizer", map[string]any{"question": strings.Repeat("x", 3000)}); code != 400 {
		t.Errorf("long question: %d", code)
	}
	if code, out := postAudio(t, srv.URL+path, email, "organizer", bytes.Repeat([]byte{0}, 200)); code != 413 {
		t.Errorf("big audio: %d %s", code, out)
	}
	if code, _ := postAudio(t, srv.URL+path, email, "organizer", []byte("%PDF-1.4 not audio")); code != 400 {
		t.Errorf("non-audio: %d", code)
	}
	wav := append([]byte("RIFF\x24\x00\x00\x00WAVEfmt "), make([]byte, 20)...)
	code, out := postAudio(t, srv.URL+path, email, "organizer", wav)
	if code != 202 {
		t.Fatalf("audio: %d %s", code, out)
	}
	var got struct{ ID string }
	_ = json.Unmarshal([]byte(out), &got)
	var owner, audioKey string
	if err := dbtest.Pool(t).QueryRow(context.Background(),
		`SELECT owner_id::text, audio_key FROM walkthroughs WHERE id = $1::uuid`, got.ID).Scan(&owner, &audioKey); err != nil {
		t.Fatal(err)
	}
	if audioKey != "voice/"+owner+"/"+got.ID || len(files.saved[audioKey]) != len(wav) {
		t.Errorf("recording not stored under %q: %v", audioKey, files.saved)
	}
	// The second question of the day is the last one allowed.
	if code, _ := roleCall(t, srv.URL, "POST", path, email, "organizer", map[string]any{"question": "again"}); code != 202 {
		t.Errorf("second question: %d", code)
	}
	if code, _ := roleCall(t, srv.URL, "POST", path, email, "organizer", map[string]any{"question": "too many"}); code != 429 {
		t.Errorf("over the daily limit: %d, want 429", code)
	}
}

func TestWalkthroughAnswerGetsViewLinksAndIsPrivate(t *testing.T) {
	srv, _ := setupWalkthrough(t, apihttp.WalkthroughLimits{AudioMaxBytes: 100, QuestionsPerDay: 10})
	email := "walkv-" + uuid.NewString()[:8] + "@example.com"
	project := walkProject(t, srv, email)
	code, out := roleCall(t, srv.URL, "POST", "/v1/projects/"+project+"/walkthroughs", email, "organizer", map[string]any{"question": "how?"})
	var w struct{ ID string }
	_ = json.Unmarshal([]byte(out), &w)
	if code != 202 {
		t.Fatalf("ask: %d %s", code, out)
	}
	_, err := dbtest.Pool(t).Exec(context.Background(), `UPDATE walkthroughs SET status = 'done', answered_at = now(), answer = $2::jsonb
		WHERE id = $1::uuid`, w.ID, `{"flow":[{"text":"a","proof":[{"kind":"screenshot","key":"screens/p/r/1"},{"kind":"code","path":"a.py"}]}],
		"seen":[],"missing":[],"label":"x"}`)
	if err != nil {
		t.Fatal(err)
	}
	code, out = roleCall(t, srv.URL, "GET", "/v1/walkthroughs/"+w.ID, email, "organizer", nil)
	if code != 200 || strings.Contains(out, `"key"`) || !strings.Contains(out, `"view_url":"https://files.example/view/screens/p/r/1`) ||
		!strings.Contains(out, `"status":"done"`) || !strings.Contains(out, `"answered_at":"20`) {
		t.Errorf("answer: %d %s", code, out)
	}
	if code, _ := roleCall(t, srv.URL, "GET", "/v1/walkthroughs/"+w.ID, "other-"+email, "organizer", nil); code != 404 {
		t.Errorf("stranger: %d, want 404", code)
	}
}

func TestTeamGithubHandlesAreCleanedAndReturned(t *testing.T) {
	srv, _ := setupWalkthrough(t, apihttp.WalkthroughLimits{})
	email := "handles-" + uuid.NewString()[:8] + "@example.com"
	code, out := roleCall(t, srv.URL, "POST", "/v1/events", email, "organizer", eventBody())
	event := idOf(t, code, out)
	post := func(handles any) (int, string) {
		return roleCall(t, srv.URL, "POST", "/v1/events/"+event+"/projects", email, "organizer",
			map[string]any{"team_name": "t", "live_url": "https://example.com", "team_github_handles": handles})
	}
	code, out = post([]string{" @Asha ", "ravi-k", "asha", ""})
	if code != 201 || !strings.Contains(out, `"team_github_handles":["asha","ravi-k"]`) {
		t.Fatalf("create: %d %s", code, out)
	}
	var p struct{ ID string }
	_ = json.Unmarshal([]byte(out), &p)
	code, out = roleCall(t, srv.URL, "GET", "/v1/projects/"+p.ID, email, "organizer", nil)
	if code != 200 || !strings.Contains(out, `"team_github_handles":["asha","ravi-k"]`) {
		t.Errorf("read: %d %s", code, out)
	}
	for _, bad := range [][]string{{"-bad"}, {"has space"}, {"a--b"}, {strings.Repeat("a", 40)},
		{"a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9", "b1", "b2"}} {
		if code, out := post(bad); code != 400 {
			t.Errorf("%v: %d %s, want 400", bad, code, out)
		}
	}
	if code, out := roleCall(t, srv.URL, "POST", "/v1/events/"+event+"/projects", email, "organizer",
		map[string]any{"team_name": "t2", "live_url": "https://example.com"}); code != 201 || !strings.Contains(out, `"team_github_handles":[]`) {
		t.Errorf("no handles: %d %s", code, out)
	}
}
