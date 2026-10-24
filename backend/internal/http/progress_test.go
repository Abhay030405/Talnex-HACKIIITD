package http_test

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	apihttp "github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/http"
)

type fakeRemover struct {
	mu       sync.Mutex
	prefixes []string
}

func (f *fakeRemover) DeletePrefix(_ context.Context, prefix string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.prefixes = append(f.prefixes, prefix)
	return nil
}

func seedJob(t *testing.T, pool *pgxpool.Pool, jobType, targetType, target, pipeline, status string, run int, errText string) {
	t.Helper()
	_, err := pool.Exec(context.Background(), `
		INSERT INTO jobs (job_type, runner, target_type, target_id, pipeline, run_number, status, error, input)
		VALUES ($1, 'python', $2, $3::uuid, $4, $5, $6, NULLIF($7, ''), '{"secret":"PERSONAL"}')`,
		jobType, targetType, target, pipeline, run, status, errText)
	if err != nil {
		t.Fatal(err)
	}
}

func seedProject(t *testing.T, pool *pgxpool.Pool, cand, name string) string {
	t.Helper()
	var id string
	if err := pool.QueryRow(context.Background(),
		`INSERT INTO candidate_projects (candidate_id, name) VALUES ($1::uuid, $2) RETURNING id::text`, cand, name).Scan(&id); err != nil {
		t.Fatal(err)
	}
	return id
}

func count(t *testing.T, pool *pgxpool.Pool, sql string, args ...any) int {
	t.Helper()
	var n int
	if err := pool.QueryRow(context.Background(), sql, args...).Scan(&n); err != nil {
		t.Fatal(err)
	}
	return n
}

type progressBody struct {
	Status       string `json:"status"`
	StatusDetail string `json:"status_detail"`
	Stages       []struct {
		Name, State, Note string
	} `json:"stages"`
	Projects []struct {
		ID, Name string
		Stages   []struct{ Name, State, Note string }
	} `json:"projects"`
	ReportReady bool `json:"report_ready"`
}

func setupProgress(t *testing.T) (*httptest.Server, *pgxpool.Pool, *fakeRemover) {
	t.Helper()
	pool := dbtest.Pool(t)
	rm := &fakeRemover{}
	srv := httptest.NewServer(apihttp.NewHandler(apihttp.Options{
		Pool: pool, AuthSecret: secret, WebOrigin: "http://localhost:3000", FileRemover: rm,
		Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
	}))
	t.Cleanup(srv.Close)
	return srv, pool, rm
}

func TestProgressStatesAndOrder(t *testing.T) {
	srv, pool, _ := setupProgress(t)
	run := uuid.NewString()[:8]
	rec, other := "prog-rec-"+run+"@example.com", "prog-other-"+run+"@example.com"
	code, out := roleCall(t, srv.URL, "POST", "/v1/candidates", rec, "recruiter", map[string]any{"label": "A"})
	cand := idOf(t, code, out)
	code, out = roleCall(t, srv.URL, "POST", "/v1/candidates", other, "recruiter", map[string]any{"label": "B"})
	otherCand := idOf(t, code, out)
	p1 := seedProject(t, pool, cand, "First")
	p2 := seedProject(t, pool, cand, "Second")
	otherProj := seedProject(t, pool, otherCand, "Elsewhere")

	// This is the second check of the candidate (a new resume): only run 2 shows. Run 1 left a failed
	// resume_read and a finished claims stage that must not appear.
	seedJob(t, pool, "resume_read", "candidate", cand, "recruiter_candidate", "failed", 1, "old failure")
	seedJob(t, pool, "resume_read", "candidate", cand, "recruiter_candidate", "done", 2, "")
	seedJob(t, pool, "codeforces", "candidate", cand, "recruiter_coding", "running", 2, "")
	seedJob(t, pool, "candidate_report", "candidate", cand, "recruiter_report", "queued", 2, "")
	// Project level, seeded out of order.
	seedJob(t, pool, "claims", "candidate_project", p1, "recruiter", "done", 2, "")
	seedJob(t, pool, "precheck", "candidate_project", p1, "recruiter", "done", 2, "")
	seedJob(t, pool, "live_test", "candidate_project", p1, "recruiter", "retrying", 2, "")
	seedJob(t, pool, "test_plan", "candidate_project", p1, "recruiter", "failed", 1, "line one\n  line two")
	seedJob(t, pool, "test_plan", "candidate_project", p1, "recruiter", "done", 2, "")
	seedJob(t, pool, "precheck", "candidate_project", p2, "recruiter", "failed", 2, "site down\nsecond line")
	seedJob(t, pool, "claims", "candidate_project", p2, "recruiter", "done", 1, "")
	// Another candidate's jobs must never show.
	seedJob(t, pool, "resume_read", "candidate", otherCand, "recruiter_candidate", "running", 1, "")
	seedJob(t, pool, "precheck", "candidate_project", otherProj, "recruiter", "running", 1, "")

	code, out = roleCall(t, srv.URL, "GET", "/v1/candidates/"+cand+"/progress", rec, "recruiter", nil)
	if code != 200 {
		t.Fatalf("progress: %d %s", code, out)
	}
	if strings.Contains(out, "PERSONAL") || strings.Contains(out, otherProj) || strings.Contains(out, "Elsewhere") {
		t.Fatalf("progress leaks something: %s", out)
	}
	var p progressBody
	if err := json.Unmarshal([]byte(out), &p); err != nil {
		t.Fatal(err)
	}
	if p.Status != "submitted" || p.ReportReady {
		t.Errorf("status %q report_ready %v", p.Status, p.ReportReady)
	}
	var got []string
	for _, s := range p.Stages {
		got = append(got, s.Name+":"+s.State)
	}
	if want := "resume_read:done codeforces:running candidate_report:waiting"; strings.Join(got, " ") != want {
		t.Errorf("candidate stages %v, want %s", got, want)
	}
	if len(p.Projects) != 2 || p.Projects[0].Name != "First" || p.Projects[1].Name != "Second" {
		t.Fatalf("projects: %+v", p.Projects)
	}
	got = nil
	for _, s := range p.Projects[0].Stages {
		got = append(got, s.Name+":"+s.State)
	}
	if want := "precheck:done claims:done test_plan:done live_test:retrying"; strings.Join(got, " ") != want {
		t.Errorf("project 1 stages %v, want %s", got, want)
	}
	st := p.Projects[1].Stages
	if len(st) != 1 || st[0].State != "failed" || st[0].Note != "site down second line" {
		t.Errorf("project 2 stages %+v", st)
	}

	// report_ready flips when the report exists; stages is [] not null for a fresh candidate.
	if _, err := pool.Exec(context.Background(),
		`INSERT INTO candidate_reports (candidate_id, report) VALUES ($1::uuid, '{}')`, cand); err != nil {
		t.Fatal(err)
	}
	_, out = roleCall(t, srv.URL, "GET", "/v1/candidates/"+cand+"/progress", rec, "recruiter", nil)
	if !strings.Contains(out, `"report_ready":true`) {
		t.Errorf("report_ready not true: %s", out)
	}
	_, out = roleCall(t, srv.URL, "GET", "/v1/candidates/"+otherCand+"/progress", other, "recruiter", nil)
	if !strings.Contains(out, `"stages":[{"name":"resume_read","state":"running"}]`) {
		t.Errorf("other candidate progress: %s", out)
	}
}

func TestDeleteCandidate(t *testing.T) {
	srv, pool, rm := setupProgress(t)
	run := uuid.NewString()[:8]
	rec, stranger := "del-rec-"+run+"@example.com", "del-other-"+run+"@example.com"
	code, out := roleCall(t, srv.URL, "POST", "/v1/candidates", rec, "recruiter", map[string]any{"label": "A"})
	cand := idOf(t, code, out)
	code, out = roleCall(t, srv.URL, "POST", "/v1/candidates", stranger, "recruiter", map[string]any{"label": "B"})
	keep := idOf(t, code, out)
	p1 := seedProject(t, pool, cand, "P1")
	keepProj := seedProject(t, pool, keep, "Keep")
	ctx := context.Background()
	if _, err := pool.Exec(ctx, `INSERT INTO candidate_reports (candidate_id, report) VALUES ($1::uuid, '{}')`, cand); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO claims (candidate_project_id, text, claim_group, importance, source) VALUES ($1::uuid, 'c', 'Core', 1, 'resume')`, p1); err != nil {
		t.Fatal(err)
	}
	seedJob(t, pool, "precheck", "candidate_project", p1, "recruiter", "running", 1, "")
	seedJob(t, pool, "resume_read", "candidate", cand, "recruiter_candidate", "done", 1, "")
	seedJob(t, pool, "precheck", "candidate_project", keepProj, "recruiter", "running", 1, "")

	// A stranger cannot delete it.
	if code, _ := roleCall(t, srv.URL, "DELETE", "/v1/candidates/"+cand, stranger, "recruiter", nil); code != 404 {
		t.Errorf("stranger delete: %d, want 404", code)
	}
	// Refused while running; nothing removed.
	code, out = roleCall(t, srv.URL, "DELETE", "/v1/candidates/"+cand, rec, "recruiter", nil)
	if code != 409 || !strings.Contains(out, "still running") {
		t.Fatalf("running delete: %d %s", code, out)
	}
	if len(rm.prefixes) != 0 || count(t, pool, `SELECT count(*) FROM candidates WHERE id = $1::uuid`, cand) != 1 {
		t.Fatalf("a refused delete removed something: %v", rm.prefixes)
	}

	// Finished: delete works.
	if _, err := pool.Exec(ctx, `UPDATE jobs SET status = 'done' WHERE target_id = $1::uuid`, p1); err != nil {
		t.Fatal(err)
	}
	if code, out = roleCall(t, srv.URL, "DELETE", "/v1/candidates/"+cand, rec, "recruiter", nil); code != 204 {
		t.Fatalf("delete: %d %s", code, out)
	}
	if want := []string{"resumes/" + cand + "/", "screens/" + p1 + "/"}; strings.Join(rm.prefixes, ",") != strings.Join(want, ",") {
		t.Errorf("removed prefixes %v, want %v", rm.prefixes, want)
	}
	for _, q := range []string{
		`SELECT count(*) FROM candidates WHERE id = $1::uuid`,
		`SELECT count(*) FROM candidate_projects WHERE candidate_id = $1::uuid`,
		`SELECT count(*) FROM candidate_reports WHERE candidate_id = $1::uuid`,
		`SELECT count(*) FROM claims WHERE candidate_project_id = $1::uuid`,
		`SELECT count(*) FROM jobs WHERE target_id = $1::uuid OR target_id = $2::uuid`,
	} {
		n := 0
		if strings.Contains(q, "claims") {
			n = count(t, pool, q, p1)
		} else if strings.Contains(q, "$2") {
			n = count(t, pool, q, cand, p1)
		} else {
			n = count(t, pool, q, cand)
		}
		if n != 0 {
			t.Errorf("rows left after delete (%s): %d", q, n)
		}
	}
	// The other candidate is untouched.
	if count(t, pool, `SELECT count(*) FROM candidates WHERE id = $1::uuid`, keep) != 1 ||
		count(t, pool, `SELECT count(*) FROM jobs WHERE target_id = $1::uuid`, keepProj) != 1 {
		t.Error("another candidate was touched")
	}
	// Second delete: 404.
	if code, _ = roleCall(t, srv.URL, "DELETE", "/v1/candidates/"+cand, rec, "recruiter", nil); code != 404 {
		t.Errorf("second delete: %d, want 404", code)
	}
}
