package http_test

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
)

func newRecruiter() string { return "role-rec-" + uuid.NewString()[:8] + "@example.com" }

func TestARoleIsSavedWithItsCriteriaAndCandidatesJoinIt(t *testing.T) {
	srv, pool, _ := setupProgress(t)
	rec := newRecruiter()
	code, out := roleCall(t, srv.URL, "POST", "/v1/roles", rec, "recruiter", map[string]any{
		"title": "  Backend   intern ", "job_description": "Build APIs in Go.", "person_wanted": "Ships small, tested changes.",
		"skills": []string{"Go", "PostgreSQL", "go", ""}, "role_level": "junior",
		"criteria": []map[string]any{{"name": "Backend", "weight": 3}, {"name": "UI", "weight": 1}},
		"checks":   map[string]bool{"live_test": true, "coding_profiles": false},
	})
	role := idOf(t, code, out)

	code, out = roleCall(t, srv.URL, "POST", "/v1/candidates", rec, "recruiter", map[string]any{"label": "A", "role_id": role})
	cand := idOf(t, code, out)
	cleanJobs(t, pool, cand)

	code, out = roleCall(t, srv.URL, "GET", "/v1/roles/"+role, rec, "recruiter", nil)
	var got struct {
		Title       string   `json:"title"`
		Skills      []string `json:"skills"`
		AutoConfirm bool     `json:"auto_confirm"`
		Criteria    []struct {
			Name   string  `json:"name"`
			Weight float64 `json:"weight"`
		} `json:"criteria"`
		Checks     map[string]bool `json:"checks"`
		Candidates []struct {
			ID        string `json:"id"`
			RoleLevel string `json:"role_level"`
			RoleID    string `json:"role_id"`
		} `json:"candidates"`
	}
	if code != 200 || json.Unmarshal([]byte(out), &got) != nil {
		t.Fatalf("get role = %d %s", code, out)
	}
	if got.Title != "Backend intern" || len(got.Skills) != 2 || !got.AutoConfirm || len(got.Criteria) != 2 ||
		got.Criteria[0].Name != "Backend" || got.Criteria[0].Weight != 3 || got.Checks["coding_profiles"] {
		t.Errorf("role = %+v", got)
	}
	if len(got.Candidates) != 1 || got.Candidates[0].ID != cand || got.Candidates[0].RoleLevel != "junior" || got.Candidates[0].RoleID != role {
		t.Errorf("the candidate should join the role with its level: %+v", got.Candidates)
	}

	code, out = roleCall(t, srv.URL, "GET", "/v1/roles", rec, "recruiter", nil)
	var list []struct {
		ID    string `json:"id"`
		Count int    `json:"candidate_count"`
	}
	if code != 200 || json.Unmarshal([]byte(out), &list) != nil || len(list) != 1 || list[0].ID != role || list[0].Count != 1 {
		t.Errorf("list roles = %d %s", code, out)
	}
}

func TestRolesAreCheckedAndPrivate(t *testing.T) {
	srv, _, _ := setupProgress(t)
	rec, other := newRecruiter(), newRecruiter()
	for _, bad := range []map[string]any{
		{"title": ""},
		{"title": "x", "checks": map[string]bool{"mind_reading": true}},
		{"title": "x", "criteria": []map[string]any{{"name": "A", "weight": 0}}},
		{"title": "x", "criteria": []map[string]any{{"name": "A", "weight": 1}, {"name": "a", "weight": 2}}},
	} {
		if code, out := roleCall(t, srv.URL, "POST", "/v1/roles", rec, "recruiter", bad); code != 400 {
			t.Errorf("%v: got %d %s, want 400", bad, code, out)
		}
	}
	code, out := roleCall(t, srv.URL, "POST", "/v1/roles", rec, "recruiter", map[string]any{"title": "Mine"})
	role := idOf(t, code, out)
	if code, _ := roleCall(t, srv.URL, "GET", "/v1/roles/"+role, other, "recruiter", nil); code != 404 {
		t.Errorf("another recruiter read the role: %d", code)
	}
	if code, _ := roleCall(t, srv.URL, "POST", "/v1/candidates", other, "recruiter", map[string]any{"role_id": role}); code != 400 {
		t.Errorf("another recruiter used the role: %d", code)
	}
	if code, _ := roleCall(t, srv.URL, "GET", "/v1/roles/not-an-id", rec, "recruiter", nil); code != 404 {
		t.Errorf("a bad id: %d", code)
	}
}

func runAutoConfirm(t *testing.T, pool *pgxpool.Pool, cand string) map[string]any {
	t.Helper()
	out, err := pipeline.AutoConfirm(pool)(context.Background(), &jobs.Job{TargetType: "candidate", TargetID: cand})
	if err != nil {
		t.Fatal(err)
	}
	return out
}

func TestAutoConfirmStartsTheChecksOnlyForARoleThatAsksForIt(t *testing.T) {
	srv, pool, _ := setupProgress(t)
	rec := newRecruiter()
	code, out := roleCall(t, srv.URL, "POST", "/v1/roles", rec, "recruiter", map[string]any{"title": "Bulk"})
	role := idOf(t, code, out)

	code, out = roleCall(t, srv.URL, "POST", "/v1/candidates", rec, "recruiter", map[string]any{"label": "In role", "role_id": role})
	cand := idOf(t, code, out)
	cleanJobs(t, pool, cand)
	project := seedProject(t, pool, cand, "TinyTools")
	seedJob(t, pool, "resume_read", "candidate", cand, "recruiter_candidate", "done", 1, "")
	setStatus(t, pool, cand, "awaiting_confirmation")

	if got := runAutoConfirm(t, pool, cand); got["started"] != true {
		t.Fatalf("auto confirm = %v", got)
	}
	var status string
	if err := pool.QueryRow(context.Background(), `SELECT status FROM candidates WHERE id = $1::uuid`, cand).Scan(&status); err != nil || status != "prechecking" {
		t.Errorf("status = %q (%v), want prechecking", status, err)
	}
	if queuedFor(t, pool, project) == 0 {
		t.Error("the project's checks were not started")
	}
	if got := runAutoConfirm(t, pool, cand); got["skipped"] != true {
		t.Errorf("running it again should change nothing: %v", got)
	}

	// Without a role the recruiter confirms by hand, as before.
	code, out = roleCall(t, srv.URL, "POST", "/v1/candidates", rec, "recruiter", map[string]any{"label": "Alone"})
	alone := idOf(t, code, out)
	cleanJobs(t, pool, alone)
	seedProject(t, pool, alone, "Solo")
	setStatus(t, pool, alone, "awaiting_confirmation")
	if got := runAutoConfirm(t, pool, alone); got["skipped"] != true {
		t.Errorf("a candidate without a role was confirmed: %v", got)
	}
}
