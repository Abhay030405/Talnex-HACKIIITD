package http_test

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	apihttp "github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/http"
)

type tourStarted struct {
	ID        string `json:"id"`
	MessageID string `json:"message_id"`
}

func TestGuidedTourChat(t *testing.T) {
	pool := dbtest.Pool(t)
	srv := httptest.NewServer(apihttp.NewHandler(apihttp.Options{
		Pool: pool, AuthSecret: secret, WebOrigin: "http://localhost:3000",
		Files: &fakeFiles{saved: map[string][]byte{}}, ProofLinks: fakeLinks{}, Tour: apihttp.TourLimits{PerDay: 2},
		Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
	}))
	defer srv.Close()
	run := uuid.NewString()[:8]
	org, stranger := "tour-org-"+run+"@example.com", "tour-other-"+run+"@example.com"

	code, out := roleCall(t, srv.URL, "POST", "/v1/events", org, "organizer", eventBody())
	eventID := idOf(t, code, out)
	code, out = roleCall(t, srv.URL, "POST", "/v1/events/"+eventID+"/projects", org, "organizer",
		map[string]any{"team_name": "t", "live_url": "https://example.com"})
	projectID := idOf(t, code, out)
	roleCall(t, srv.URL, "GET", "/v1/me", stranger, "organizer", nil)

	// An empty question is refused; a good one starts a chat and adds exactly one job for it.
	if code, out := roleCall(t, srv.URL, "POST", "/v1/projects/"+projectID+"/tours", org, "organizer", map[string]any{"question": "  "}); code != 400 {
		t.Fatalf("empty question: %d %s", code, out)
	}
	code, out = roleCall(t, srv.URL, "POST", "/v1/projects/"+projectID+"/tours", org, "organizer", map[string]any{"question": "How does the todo list work?"})
	if code != 202 {
		t.Fatalf("start: %d %s", code, out)
	}
	var first tourStarted
	_ = json.Unmarshal([]byte(out), &first)
	var jobs, tries int
	var limit int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*), max(max_tries), max(time_limit_seconds) FROM jobs WHERE job_type = 'tour_message' AND input->>'message_id' = $1`,
		first.MessageID).Scan(&jobs, &tries, &limit); err != nil {
		t.Fatal(err)
	}
	if jobs != 1 || tries != 1 || limit < 600 {
		t.Errorf("the tour job: %d jobs, %d tries, %d s; want one job, one try and a long limit", jobs, tries, limit)
	}

	// One question at a time: the second is refused until the first is answered.
	path := "/v1/tours/" + first.ID + "/messages"
	if code, out := roleCall(t, srv.URL, "POST", path, org, "organizer", map[string]any{"question": "and the login?"}); code != 409 {
		t.Fatalf("second question while busy: %d %s, want 409", code, out)
	}
	answer := `{"say":[{"text":"It saves items.","proof":[{"kind":"screenshot","key":"screens/p/r/1"},{"kind":"code","file":"app.js","start":3,"end":9}]}],"label":"AI explanation"}`
	if _, err := pool.Exec(context.Background(),
		`UPDATE tour_messages SET status = 'done', answer = $2::jsonb, answered_at = now() WHERE id = $1::uuid`, first.MessageID, answer); err != nil {
		t.Fatal(err)
	}
	if code, out := roleCall(t, srv.URL, "POST", path, org, "organizer", map[string]any{"question": "and the login?"}); code != 202 {
		t.Fatalf("second question: %d %s", code, out)
	}

	// The chat shows both questions; the answer's screenshot key is swapped for a view link, never shown raw.
	code, out = roleCall(t, srv.URL, "GET", "/v1/tours/"+first.ID, org, "organizer", nil)
	if code != 200 || strings.Count(out, `"question"`) != 2 {
		t.Fatalf("read chat: %d %s", code, out)
	}
	if strings.Contains(out, `"key":"screens/`) || !strings.Contains(out, "view_url") {
		t.Errorf("the screenshot key must become a view link: %s", out)
	}

	// The daily limit counts chats per project (2 here): the second chat is fine, the third is not.
	if code, out := roleCall(t, srv.URL, "POST", "/v1/projects/"+projectID+"/tours", org, "organizer", map[string]any{"question": "again"}); code != 202 {
		t.Fatalf("second chat: %d %s", code, out)
	}
	if code, out := roleCall(t, srv.URL, "POST", "/v1/projects/"+projectID+"/tours", org, "organizer", map[string]any{"question": "once more"}); code != 429 {
		t.Fatalf("third chat: %d %s, want 429", code, out)
	}
}
