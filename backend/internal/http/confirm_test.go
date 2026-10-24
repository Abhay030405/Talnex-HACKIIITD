package http_test

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func setStatus(t *testing.T, pool *pgxpool.Pool, cand, status string) {
	t.Helper()
	if _, err := pool.Exec(context.Background(), `UPDATE candidates SET status = $2 WHERE id = $1::uuid`, cand, status); err != nil {
		t.Fatal(err)
	}
}

// cleanJobs removes the jobs a test queued for a candidate and its projects, so other tests see an empty queue.
func cleanJobs(t *testing.T, pool *pgxpool.Pool, cand string) {
	t.Helper()
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `
			DELETE FROM jobs WHERE target_id = $1::uuid
			   OR target_id IN (SELECT id FROM candidate_projects WHERE candidate_id = $1::uuid)`, cand)
	})
}

func queuedFor(t *testing.T, pool *pgxpool.Pool, target string) int {
	t.Helper()
	return count(t, pool, `SELECT count(*) FROM jobs WHERE target_id = $1::uuid`, target)
}

func TestConfirmShowsWhatWasFoundThenStartsTheChecks(t *testing.T) {
	srv, pool, _ := setupProgress(t)
	rec := "confirm-rec-" + uuid.NewString()[:8] + "@example.com"
	code, out := roleCall(t, srv.URL, "POST", "/v1/candidates", rec, "recruiter", map[string]any{"label": "A"})
	cand := idOf(t, code, out)
	cleanJobs(t, pool, cand)
	keep := seedProject(t, pool, cand, "TinyTools")
	drop := seedProject(t, pool, cand, "Misread")
	seedJob(t, pool, "resume_read", "candidate", cand, "recruiter_candidate", "done", 2, "")
	setStatus(t, pool, cand, "awaiting_confirmation")
	if _, err := pool.Exec(context.Background(), `
		UPDATE candidates SET coding_handles = '{"leetcode":"asha_lc"}', coding_links = '{"leetcode":"https://leetcode.com/u/asha_lc"}'
		 WHERE id = $1::uuid`, cand); err != nil {
		t.Fatal(err)
	}

	// What was found.
	code, out = roleCall(t, srv.URL, "GET", "/v1/candidates/"+cand+"/found", rec, "recruiter", nil)
	var found struct {
		Status   string `json:"status"`
		Projects []struct{ ID, Name string }
		Links    map[string]string `json:"coding_links"`
	}
	if code != 200 || json.Unmarshal([]byte(out), &found) != nil || found.Status != "awaiting_confirmation" ||
		len(found.Projects) != 2 || found.Links["leetcode"] != "https://leetcode.com/u/asha_lc" {
		t.Fatalf("found = %d %s", code, out)
	}

	// The recruiter fixes one link, removes a wrong project, adds one by hand, and corrects a profile.
	body := map[string]any{
		"projects": []map[string]any{
			{"id": keep, "name": "TinyTools", "live_url": "talnex-honest.vercel.app", "repo_url": "https://github.com/x/tinytools"},
			{"name": "Added by hand", "live_url": "https://example.com/app"},
		},
		"coding_profiles": map[string]string{"leetcode": "https://leetcode.com/u/asha_fixed/", "codeforces": "", "codechef": "asha_cc"},
	}
	code, out = roleCall(t, srv.URL, "POST", "/v1/candidates/"+cand+"/confirm", rec, "recruiter", body)
	if code != 202 {
		t.Fatalf("confirm = %d %s", code, out)
	}

	if n := count(t, pool, `SELECT count(*) FROM candidate_projects WHERE id = $1::uuid`, drop); n != 0 {
		t.Error("the removed project is still there")
	}
	var live, handles, links, status string
	if err := pool.QueryRow(context.Background(), `SELECT live_url FROM candidate_projects WHERE id = $1::uuid`, keep).Scan(&live); err != nil || live != "https://talnex-honest.vercel.app" {
		t.Errorf("fixed live link = %q (%v)", live, err)
	}
	if err := pool.QueryRow(context.Background(), `SELECT coding_handles::text, coding_links::text, status FROM candidates WHERE id = $1::uuid`, cand).Scan(&handles, &links, &status); err != nil {
		t.Fatal(err)
	}
	if status != "prechecking" || !strings.Contains(handles, `"asha_fixed"`) || !strings.Contains(handles, `"asha_cc"`) || strings.Contains(handles, "codeforces") ||
		!strings.Contains(links, "https://leetcode.com/u/asha_fixed") {
		t.Errorf("candidate = %s %s %s", status, handles, links)
	}

	// The checks use the run number of the resume read (2), for the added project too.
	if n := count(t, pool, `SELECT count(*) FROM jobs WHERE pipeline = 'recruiter' AND job_type = 'precheck' AND run_number = 2`); n < 2 {
		t.Errorf("project checks started = %d, want at least 2", n)
	}
	if n := count(t, pool, `SELECT count(*) FROM jobs WHERE pipeline = 'recruiter_coding' AND target_id = $1::uuid AND run_number = 2`, cand); n == 0 {
		t.Error("coding checks were not started")
	}
	if queuedFor(t, pool, keep) == 0 {
		t.Error("no job for the kept project")
	}

	// Confirming a second time is refused, and adds nothing.
	before := count(t, pool, `SELECT count(*) FROM jobs`)
	code, _ = roleCall(t, srv.URL, "POST", "/v1/candidates/"+cand+"/confirm", rec, "recruiter", body)
	if code != 409 || count(t, pool, `SELECT count(*) FROM jobs`) != before {
		t.Errorf("second confirm = %d, jobs changed = %v", code, count(t, pool, `SELECT count(*) FROM jobs`) != before)
	}
}

func TestConfirmRefusesBadInputAndOtherPeoplesProjects(t *testing.T) {
	srv, pool, _ := setupProgress(t)
	run := uuid.NewString()[:8]
	rec, other := "confirm-bad-"+run+"@example.com", "confirm-other-"+run+"@example.com"
	code, out := roleCall(t, srv.URL, "POST", "/v1/candidates", rec, "recruiter", map[string]any{"label": "A"})
	cand := idOf(t, code, out)
	code, out = roleCall(t, srv.URL, "POST", "/v1/candidates", other, "recruiter", map[string]any{"label": "B"})
	otherCand := idOf(t, code, out)
	cleanJobs(t, pool, cand)
	cleanJobs(t, pool, otherCand)
	foreign := seedProject(t, pool, otherCand, "Theirs")
	setStatus(t, pool, cand, "awaiting_confirmation")
	setStatus(t, pool, otherCand, "awaiting_confirmation")

	cases := []struct {
		name string
		body map[string]any
		want string
	}{
		{"no project", map[string]any{"projects": []map[string]any{}}, "at least one project"},
		{"no name", map[string]any{"projects": []map[string]any{{"name": "  "}}}, "needs a name"},
		{"bad link", map[string]any{"projects": []map[string]any{{"name": "A", "live_url": "not a link"}}}, "not a web address"},
		{"javascript link", map[string]any{"projects": []map[string]any{{"name": "A", "live_url": "javascript:alert(1)"}}}, "not a web address"},
		{"same name twice", map[string]any{"projects": []map[string]any{{"name": "A"}, {"name": "a"}}}, "two projects"},
		{"wrong site", map[string]any{"projects": []map[string]any{{"name": "A"}}, "coding_profiles": map[string]string{"leetcode": "https://codeforces.com/profile/x"}}, "not a leetcode.com profile"},
		{"foreign project", map[string]any{"projects": []map[string]any{{"id": foreign, "name": "Theirs"}}}, "does not belong"},
	}
	for _, c := range cases {
		code, out := roleCall(t, srv.URL, "POST", "/v1/candidates/"+cand+"/confirm", rec, "recruiter", c.body)
		if code != 400 || !strings.Contains(out, c.want) {
			t.Errorf("%s: %d %s (wanted %q)", c.name, code, out, c.want)
		}
	}
	if st := count(t, pool, `SELECT count(*) FROM candidates WHERE id = $1::uuid AND status = 'awaiting_confirmation'`, cand); st != 1 {
		t.Error("a refused confirmation must leave the check waiting")
	}
	if n := count(t, pool, `SELECT count(*) FROM candidate_projects WHERE id = $1::uuid AND candidate_id = $2::uuid`, foreign, otherCand); n != 1 {
		t.Error("someone else's project was touched")
	}

	// A check that is not waiting cannot be confirmed.
	setStatus(t, pool, cand, "testing")
	code, _ = roleCall(t, srv.URL, "POST", "/v1/candidates/"+cand+"/confirm", rec, "recruiter",
		map[string]any{"projects": []map[string]any{{"name": "A"}}})
	if code != 409 {
		t.Errorf("confirm while testing = %d, want 409", code)
	}
}
