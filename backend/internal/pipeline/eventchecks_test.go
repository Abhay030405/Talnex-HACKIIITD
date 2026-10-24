package pipeline_test

import (
	"context"
	"encoding/base64"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
)

// The event runs 1 Nov 09:00 to 2 Nov 09:00 2026.
const eventStart = "2026-11-01T09:00:00Z"

// fakeTeamRepo answers like api.github.com for one team's repository: created before the event, a starter app
// committed before the start, then a big change near the deadline.
func fakeTeamRepo(t *testing.T) *github.Client {
	t.Helper()
	mux := http.NewServeMux()
	write := func(w http.ResponseWriter, body string) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}
	mux.HandleFunc("/repos/team/app", func(w http.ResponseWriter, _ *http.Request) {
		write(w, `{"full_name":"team/app","default_branch":"main","created_at":"2026-10-20T10:00:00Z","pushed_at":"2026-11-02T08:00:00Z"}`)
	})
	mux.HandleFunc("/repos/team/app/commits", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("until") != "" { // the last commit before the event began
			write(w, `[{"sha":"oldsha","commit":{"committer":{"date":"2026-10-30T10:00:00Z"}}}]`)
			return
		}
		write(w, `[{"sha":"newsha","commit":{"committer":{"date":"2026-11-02T08:30:00Z"}}},
			{"sha":"oldsha","commit":{"committer":{"date":"2026-10-30T10:00:00Z"}}}]`)
	})
	mux.HandleFunc("/repos/team/app/git/trees/main", func(w http.ResponseWriter, _ *http.Request) {
		write(w, `{"truncated":false,"tree":[{"path":"app.js","type":"blob","sha":"a1","size":800},
			{"path":"extra.js","type":"blob","sha":"e1","size":200},{"path":"package.json","type":"blob","sha":"p1","size":50}]}`)
	})
	mux.HandleFunc("/repos/team/app/git/trees/oldsha", func(w http.ResponseWriter, _ *http.Request) {
		write(w, `{"truncated":false,"tree":[{"path":"app.js","type":"blob","sha":"a1","size":800},
			{"path":"package.json","type":"blob","sha":"p1","size":50}]}`)
	})
	mux.HandleFunc("/repos/team/app/contents/package.json", func(w http.ResponseWriter, _ *http.Request) {
		body := base64.StdEncoding.EncodeToString([]byte(`{"dependencies":{"@stripe/stripe-js":"1","react":"18"}}`))
		write(w, `{"type":"file","size":50,"encoding":"base64","content":"`+body+`"}`)
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return github.NewClient(srv.URL, "test-token")
}

// hackathonProject makes an event with sponsor tools and one project, returning the project's id.
func hackathonProject(t *testing.T, repo string, sponsors []string) string {
	t.Helper()
	pool := dbtest.Pool(t)
	ctx := context.Background()
	if sponsors == nil {
		sponsors = []string{}
	}
	var owner, event, project string
	if err := pool.QueryRow(ctx, `INSERT INTO users (email) VALUES ($1) RETURNING id::text`, uuid.NewString()+"@example.com").Scan(&owner); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `INSERT INTO events (owner_id, name, mode, starts_at, ends_at, sponsor_tools)
		VALUES ($1::uuid, 'E', 'open_theme', $2::timestamptz, $2::timestamptz + interval '1 day', $3) RETURNING id::text`,
		owner, eventStart, sponsors).Scan(&event); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `INSERT INTO projects (event_id, team_name, repo_url) VALUES ($1::uuid, 'T', NULLIF($2, '')) RETURNING id::text`,
		event, repo).Scan(&project); err != nil {
		t.Fatal(err)
	}
	return project
}

func runStage(t *testing.T, h jobs.Handler, kind, id string) map[string]any {
	t.Helper()
	out, err := h(context.Background(), &jobs.Job{TargetType: kind, TargetID: id, RunNumber: 1})
	if err != nil {
		t.Fatalf("stage failed: %v", err)
	}
	return out
}

func TestEventDatesReportsHowMuchCodeExistedBeforeTheStart(t *testing.T) {
	pool, gh := dbtest.Pool(t), fakeTeamRepo(t)
	id := hackathonProject(t, "https://github.com/team/app", nil)
	out := runStage(t, pipeline.EventDates(pool, gh), "project", id)

	if out["found"] != true || out["repo_created_before_start"] != true || out["commits_before_start"] != true {
		t.Errorf("facts = %v", out)
	}
	// app.js (800) and package.json (50) are unchanged since before the start; extra.js (200) is new: 850 of 1050.
	if out["share_before_start_pct"] != 81.0 {
		t.Errorf("share = %v, want 81", out["share_before_start_pct"])
	}
	if out["one_big_upload"] != false { // two commits two days apart
		t.Errorf("one_big_upload = %v", out["one_big_upload"])
	}
}

func TestEventDatesWithoutARepoIsNotAnError(t *testing.T) {
	pool, gh := dbtest.Pool(t), fakeTeamRepo(t)
	for _, link := range []string{"", "https://gitlab.com/a/b", "https://github.com/nobody/missing"} {
		out := runStage(t, pipeline.EventDates(pool, gh), "project", hackathonProject(t, link, nil))
		if out["found"] != false || out["reason"] == "" {
			t.Errorf("%q: %v", link, out)
		}
	}
}

func TestChecksAreOnlyForHackathonProjects(t *testing.T) {
	pool, gh := dbtest.Pool(t), fakeTeamRepo(t)
	for _, h := range []jobs.Handler{pipeline.EventDates(pool, gh), pipeline.SponsorFiles(pool, gh)} {
		if out := runStage(t, h, "candidate_project", uuid.NewString()); out["skipped"] != true {
			t.Errorf("got %v", out)
		}
	}
}

func TestSponsorFilesFindsListedToolsAndNamesTheMissingOnes(t *testing.T) {
	pool, gh := dbtest.Pool(t), fakeTeamRepo(t)
	id := hackathonProject(t, "https://github.com/team/app", []string{"Stripe", "Twilio"})

	// The GitHub data stage ran first and saved the default branch and the dependency files.
	if _, err := pool.Exec(context.Background(), `
		INSERT INTO jobs (job_type, runner, target_type, target_id, pipeline, run_number, status, result, dedupe_key)
		VALUES ('github_check', 'go', 'project', $1::uuid, 'hackathon', 1, 'done',
		        '{"found":true,"default_branch":"main","dependency_files":["package.json"]}', $1::text || ':github_check')`, id); err != nil {
		t.Fatal(err)
	}
	h := pipeline.SponsorFiles(pool, gh)
	out, err := h(context.Background(), &jobs.Job{TargetType: "project", TargetID: id, RunNumber: 1, Pipeline: strPtr("hackathon")})
	if err != nil {
		t.Fatal(err)
	}
	tools := out["tools"].([]map[string]any)
	if len(tools) != 2 || tools[0]["tool"] != "Stripe" || tools[0]["listed"] != true || tools[1]["tool"] != "Twilio" || tools[1]["listed"] != false {
		t.Errorf("tools = %v", tools)
	}
}

func TestSponsorFilesWithNoSponsorsIsSkipped(t *testing.T) {
	pool, gh := dbtest.Pool(t), fakeTeamRepo(t)
	id := hackathonProject(t, "https://github.com/team/app", nil)
	if out := runStage(t, pipeline.SponsorFiles(pool, gh), "project", id); out["skipped"] != true {
		t.Errorf("got %v", out)
	}
}

func strPtr(s string) *string { return &s }
