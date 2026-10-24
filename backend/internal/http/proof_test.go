package http_test

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	apihttp "github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/http"
)

type viewLinks struct{}

func (viewLinks) ViewLink(_ context.Context, key string) (string, error) {
	return "https://files.example/view/" + key + "?sig=abc", nil
}

func setupProof(t *testing.T) *httptest.Server {
	t.Helper()
	h := apihttp.NewHandler(apihttp.Options{
		Pool: dbtest.Pool(t), AuthSecret: secret, WebOrigin: "http://localhost:3000",
		ProofLinks: viewLinks{}, Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
	})
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return srv
}

const sampleCard = `{"version":1,"team_name":"Team Shelf","features":[
 {"text":"adds a book","proof":[{"step":1,"action":"POST /api/books","observed":"pass","proof_key":"sandbox/p/r/step-1.json"},
                               {"step":2,"action":"no file","observed":"x"}]},
 {"text":"no proof at all"}],"flags":[],"groups":[]}`

func saveCard(t *testing.T, project string, hasGaps bool) {
	t.Helper()
	_, err := dbtest.Pool(t).Exec(context.Background(), `
		INSERT INTO project_reports (project_id, report, has_gaps) VALUES ($1::uuid, $2::jsonb, $3)
		ON CONFLICT (project_id) DO UPDATE SET report = EXCLUDED.report, has_gaps = EXCLUDED.has_gaps`, project, sampleCard, hasGaps)
	if err != nil {
		t.Fatal(err)
	}
}

func TestTheProofCardSwapsStorageKeysForViewLinksAndIsPrivateToTheOwner(t *testing.T) {
	srv := setupProof(t)
	event := makeEvent(t, srv.URL, "proof-a@example.com", eventBody())
	project := makeProject(t, srv.URL, "proof-a@example.com", event, "shelf")

	if resp, out := call(t, "GET", srv.URL+"/v1/projects/"+project+"/proof", "proof-a@example.com", nil); resp.StatusCode != 404 ||
		!strings.Contains(string(out), "not ready") {
		t.Fatalf("before the card exists: %d %s", resp.StatusCode, out)
	}
	saveCard(t, project, true)
	resp, out := call(t, "GET", srv.URL+"/v1/projects/"+project+"/proof", "proof-a@example.com", nil)
	if resp.StatusCode != 200 {
		t.Fatalf("card: %d %s", resp.StatusCode, out)
	}
	if strings.Contains(string(out), "proof_key") || strings.Contains(string(out), "sandbox/p/r/step-1.json\"") {
		t.Errorf("a raw storage key left the server: %s", out)
	}
	var got struct {
		HasGaps     bool   `json:"has_gaps"`
		GeneratedAt string `json:"generated_at"`
		TeamName    string `json:"team_name"`
		Features    []struct {
			Proof []map[string]any `json:"proof"`
		} `json:"features"`
	}
	if err := json.Unmarshal(out, &got); err != nil {
		t.Fatal(err)
	}
	if !got.HasGaps || got.GeneratedAt == "" || got.TeamName != "Team Shelf" {
		t.Errorf("card = %+v", got)
	}
	if url, _ := got.Features[0].Proof[0]["proof_url"].(string); !strings.HasPrefix(url, "https://files.example/view/sandbox/p/r/step-1.json") {
		t.Errorf("first step should carry a view link, got %v", got.Features[0].Proof[0])
	}
	if _, has := got.Features[0].Proof[1]["proof_url"]; has {
		t.Errorf("a step without a file must not get a link: %v", got.Features[0].Proof[1])
	}

	// A stranger gets "not found", the same answer as for a project that does not exist.
	if resp, _ := call(t, "GET", srv.URL+"/v1/projects/"+project+"/proof", "proof-b@example.com", nil); resp.StatusCode != 404 {
		t.Errorf("stranger got %d, want 404", resp.StatusCode)
	}
	if resp, _ := call(t, "GET", srv.URL+"/v1/projects/not-a-uuid/proof", "proof-a@example.com", nil); resp.StatusCode != 404 {
		t.Errorf("malformed id got %d, want 404", resp.StatusCode)
	}
	if resp, _ := call(t, "GET", srv.URL+"/v1/projects/"+project+"/proof", "", nil); resp.StatusCode != 401 {
		t.Errorf("no sign-in got %d, want 401", resp.StatusCode)
	}
}

func TestTheEventOverviewListsProjectsByNameNeverByScore(t *testing.T) {
	srv := setupProof(t)
	pool := dbtest.Pool(t)
	event := makeEvent(t, srv.URL, "overview-a@example.com", fixedEventBody())
	zeta := makeProject(t, srv.URL, "overview-a@example.com", event, "Zeta")
	alpha := makeProject(t, srv.URL, "overview-a@example.com", event, "alpha")
	ctx := context.Background()
	exec := func(sql string, args ...any) {
		t.Helper()
		if _, err := pool.Exec(ctx, sql, args...); err != nil {
			t.Fatal(err)
		}
	}
	// Zeta has the higher score and still comes last: the list is by name.
	exec(`INSERT INTO scores (project_id, score_group, score, coverage, confidence, claims_used) VALUES
	      ($1::uuid, 'talnex', 90, 100, 'high', 3), ($1::uuid, 'weighted_total', 85, 100, 'high', 2),
	      ($1::uuid, 'Setup', 100, 100, 'high', 1), ($1::uuid, 'Image captioning', 70, 40, 'low', 1),
	      ($2::uuid, 'talnex', 20, 100, 'medium', 3)`, zeta, alpha)
	exec(`INSERT INTO flags (project_id, flag_type, level, reason) VALUES ($1::uuid, 'code_before_event', 'review', 'x'),
	      ($1::uuid, 'sponsor_tech_not_used', 'review', 'y'), ($1::uuid, 'one_big_upload', 'info', 'z')`, zeta)
	saveCard(t, zeta, false)

	resp, out := call(t, "GET", srv.URL+"/v1/events/"+event+"/overview", "overview-a@example.com", nil)
	if resp.StatusCode != 200 {
		t.Fatalf("overview: %d %s", resp.StatusCode, out)
	}
	var got struct {
		Event struct {
			Name     string `json:"name"`
			Criteria []any  `json:"criteria"`
		} `json:"event"`
		Projects []struct {
			TeamName      string         `json:"team_name"`
			Status        string         `json:"status"`
			HasLive       bool           `json:"has_live"`
			TalnexScore10 *float64       `json:"talnex_score10"`
			WeightedTotal *float64       `json:"weighted_total"`
			Flags         map[string]int `json:"flags"`
			ReportReady   bool           `json:"report_ready"`
			Groups        []struct {
				Group       string  `json:"group"`
				LowCoverage bool    `json:"low_coverage"`
				Score       float64 `json:"score"`
			} `json:"groups"`
		} `json:"projects"`
	}
	if err := json.Unmarshal(out, &got); err != nil {
		t.Fatal(err)
	}
	if len(got.Projects) != 2 || got.Projects[0].TeamName != "alpha" || got.Projects[1].TeamName != "Zeta" {
		t.Fatalf("order = %+v", got.Projects)
	}
	if len(got.Event.Criteria) != 2 || got.Event.Name == "" {
		t.Errorf("event = %+v", got.Event)
	}
	a, z := got.Projects[0], got.Projects[1]
	if a.TalnexScore10 == nil || *a.TalnexScore10 != 2 || a.ReportReady || len(a.Groups) != 0 || !a.HasLive {
		t.Errorf("alpha = %+v", a)
	}
	if z.TalnexScore10 == nil || *z.TalnexScore10 != 9 || z.WeightedTotal == nil || *z.WeightedTotal != 85 || !z.ReportReady {
		t.Errorf("zeta = %+v", z)
	}
	if z.Flags["review"] != 2 || z.Flags["info"] != 1 || z.Status != "submitted" {
		t.Errorf("zeta flags/status = %+v %q", z.Flags, z.Status)
	}
	if len(z.Groups) != 2 || z.Groups[0].Group != "Image captioning" || !z.Groups[0].LowCoverage || z.Groups[1].Group != "Setup" {
		t.Errorf("zeta groups = %+v", z.Groups)
	}

	if resp, _ := call(t, "GET", srv.URL+"/v1/events/"+event+"/overview", "overview-b@example.com", nil); resp.StatusCode != 404 {
		t.Errorf("stranger got %d, want 404", resp.StatusCode)
	}
}

func TestTheCompareDataListsTopTeamsAndCopyPairsAndKeepsStorageKeysPrivate(t *testing.T) {
	srv := setupProof(t)
	pool := dbtest.Pool(t)
	event := makeEvent(t, srv.URL, "compare-a@example.com", fixedEventBody())
	one := makeProject(t, srv.URL, "compare-a@example.com", event, "Alpha")
	two := makeProject(t, srv.URL, "compare-a@example.com", event, "Beta")
	ctx := context.Background()
	if _, err := pool.Exec(ctx, `INSERT INTO feature_groups (event_id, feature_name, best_teams, kind) VALUES
	      ($1::uuid, 'Add a todo', '[{"team_name":"Alpha","verdict":"works","proof_keys":["screens/p/r/1"]}]'::jsonb, 'feature'),
	      ($1::uuid, 'Best Core', '[{"team_name":"Beta","score":88}]'::jsonb, 'group')`, event); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO copy_pairs (event_id, project_a_id, project_b_id, shared_pct, level, matching_files)
	      VALUES ($1::uuid, $2::uuid, $3::uuid, 82.5, 'strong', '[{"a_file":"a.js","b_file":"b.js"}]'::jsonb)`, event, one, two); err != nil {
		t.Fatal(err)
	}
	resp, out := call(t, "GET", srv.URL+"/v1/events/"+event+"/compare", "compare-a@example.com", nil)
	if resp.StatusCode != 200 {
		t.Fatalf("compare: %d %s", resp.StatusCode, out)
	}
	body := string(out)
	for _, want := range []string{`"ready":false`, `"name":"Add a todo"`, `"name":"Best Core"`, `"shared_pct":82.5`, `"level":"strong"`,
		`https://files.example/view/screens/p/r/1?sig=abc`} {
		if !strings.Contains(body, want) {
			t.Errorf("compare answer lacks %s: %s", want, body)
		}
	}
	if strings.Contains(body, "proof_keys") || strings.Contains(body, `"winner"`) {
		t.Errorf("a storage key or a winner leaked: %s", body)
	}
}

func TestTheOpinionScreenshotsBecomeViewLinks(t *testing.T) {
	srv := setupProof(t)
	event := makeEvent(t, srv.URL, "opinion-a@example.com", eventBody())
	project := makeProject(t, srv.URL, "opinion-a@example.com", event, "shelf")
	card := `{"version":1,"features":[],"flags":[],"groups":[],"ai_opinion":{"label":"AI opinion — not tested proof",
	  "ui":{"parts":[{"part":"clarity","score":4,"proof_key":"opinion/p/desktop"}]},"innovation":{"parts":[{"part":"new_vs_existing","score":3}]}}}`
	if _, err := dbtest.Pool(t).Exec(context.Background(), `INSERT INTO project_reports (project_id, report) VALUES ($1::uuid, $2::jsonb)`, project, card); err != nil {
		t.Fatal(err)
	}
	resp, out := call(t, "GET", srv.URL+"/v1/projects/"+project+"/proof", "opinion-a@example.com", nil)
	body := string(out)
	if resp.StatusCode != 200 || !strings.Contains(body, "https://files.example/view/opinion/p/desktop?sig=abc") || strings.Contains(body, `"proof_key"`) {
		t.Fatalf("opinion links: %d %s", resp.StatusCode, body)
	}
}
