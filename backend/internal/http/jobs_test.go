package http_test

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestJobsPanelListsRetriesAndRunsChosenStages(t *testing.T) {
	srv, pool, _ := setupProgress(t)
	ctx := context.Background()
	rec := "jobs-rec-" + uuid.NewString()[:8] + "@example.com"
	code, out := roleCall(t, srv.URL, "POST", "/v1/candidates", rec, "recruiter", map[string]any{"label": "Jobs"})
	cand := idOf(t, code, out)
	cleanJobs(t, pool, cand)
	proj := seedProject(t, pool, cand, "TinyTools")

	// Run 1 finished: every recruiter stage done, each with its own result.
	if _, err := pool.Exec(ctx, `
		INSERT INTO jobs (job_type, runner, target_type, target_id, pipeline, run_number, status, result, dedupe_key)
		SELECT stage, runner, 'candidate_project', $1::uuid, 'recruiter', 1, 'done', jsonb_build_object('stage', stage),
		       'recruiter:' || stage || ':candidate_project:' || $1 || ':1'
		  FROM pipeline_stages WHERE pipeline = 'recruiter'`, proj); err != nil {
		t.Fatal(err)
	}

	// The list shows the project's jobs with its name.
	code, out = roleCall(t, srv.URL, "GET", "/v1/candidates/"+cand+"/jobs", rec, "recruiter", nil)
	var list []struct {
		Stage, Project, Status string
		Run                    int
	}
	if code != 200 || json.Unmarshal([]byte(out), &list) != nil || len(list) == 0 || list[0].Project != "TinyTools" {
		t.Fatalf("jobs = %d %s", code, out)
	}

	// Run live_test again: earlier stages are reused as done with their results, live_test is queued, later ones wait.
	code, out = roleCall(t, srv.URL, "POST", "/v1/candidate-projects/"+proj+"/run-stages", rec, "recruiter",
		map[string]any{"stages": []string{"live_test"}})
	if code != 202 {
		t.Fatalf("run-stages = %d %s", code, out)
	}
	stateOf := func(stage string) (string, string) {
		var status, result string
		err := pool.QueryRow(ctx, `SELECT status, coalesce(result::text, '') FROM jobs
			WHERE target_id = $1::uuid AND pipeline = 'recruiter' AND run_number = 2 AND job_type = $2`, proj, stage).Scan(&status, &result)
		if err != nil {
			return "", ""
		}
		return status, result
	}
	if st, res := stateOf("test_plan"); st != "done" || !json.Valid([]byte(res)) || !strings.Contains(res, `"stage": "test_plan"`) || !strings.Contains(res, `"reused_from_run": 1`) {
		t.Errorf("test_plan in run 2 = %q %s, want done with run 1's result", st, res)
	}
	if st, _ := stateOf("live_test"); st != "queued" {
		t.Errorf("live_test = %q, want queued", st)
	}
	if st, _ := stateOf("proof_check"); st != "" {
		t.Errorf("proof_check = %q, want not yet added", st)
	}
	var status string
	_ = pool.QueryRow(ctx, `SELECT status FROM candidates WHERE id = $1::uuid`, cand).Scan(&status)
	if status != "testing" {
		t.Errorf("candidate status = %q, want testing", status)
	}

	// While it runs, another run is refused.
	if code, _ := roleCall(t, srv.URL, "POST", "/v1/candidate-projects/"+proj+"/run-stages", rec, "recruiter",
		map[string]any{"stages": []string{"claims"}}); code != 409 {
		t.Errorf("second run-stages = %d, want 409", code)
	}
	if code, _ := roleCall(t, srv.URL, "POST", "/v1/candidate-projects/"+proj+"/run-stages", rec, "recruiter",
		map[string]any{"stages": []string{"mind_reading"}}); code != 400 {
		t.Errorf("unknown stage = %d, want 400", code)
	}

	// When live_test finishes, the stage after it chains as usual.
	var liveID string
	if err := pool.QueryRow(ctx, `UPDATE jobs SET status = 'running', locked_by = 'w1' WHERE target_id = $1::uuid
		AND pipeline = 'recruiter' AND run_number = 2 AND job_type = 'live_test' RETURNING id::text`, proj).Scan(&liveID); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `SELECT complete_job($1::uuid, 'w1', '{}')`, liveID); err != nil {
		t.Fatal(err)
	}
	if st, _ := stateOf("proof_check"); st != "queued" {
		t.Errorf("proof_check after live_test = %q, want queued", st)
	}

	// Retry: only a failed job.
	var failed string
	if err := pool.QueryRow(ctx, `UPDATE jobs SET status = 'failed', error = 'boom' WHERE target_id = $1::uuid
		AND run_number = 2 AND job_type = 'proof_check' RETURNING id::text`, proj).Scan(&failed); err != nil {
		t.Fatal(err)
	}
	if code, out := roleCall(t, srv.URL, "POST", "/v1/jobs/"+failed+"/retry", rec, "recruiter", nil); code != 202 {
		t.Errorf("retry failed = %d %s", code, out)
	}
	if code, _ := roleCall(t, srv.URL, "POST", "/v1/jobs/"+failed+"/retry", rec, "recruiter", nil); code != 409 {
		t.Errorf("retry a queued job = %d, want 409", code)
	}
	stranger := "jobs-other-" + uuid.NewString()[:8] + "@example.com"
	if code, _ := roleCall(t, srv.URL, "POST", "/v1/jobs/"+failed+"/retry", stranger, "recruiter", nil); code != 404 {
		t.Errorf("stranger retry = %d, want 404", code)
	}
}
