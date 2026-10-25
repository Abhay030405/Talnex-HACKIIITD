package http_test

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/google/uuid"
)

// The resume's claimed dates, team and role are shown on the confirm page, can be fixed there, and are checked.
func TestConfirmShowsAndSavesClaimedDatesAndTeam(t *testing.T) {
	srv, pool, _ := setupProgress(t)
	rec := "claims-rec-" + uuid.NewString()[:8] + "@example.com"
	code, out := roleCall(t, srv.URL, "POST", "/v1/candidates", rec, "recruiter", map[string]any{"label": "A"})
	cand := idOf(t, code, out)
	cleanJobs(t, pool, cand)
	proj := seedProject(t, pool, cand, "ShelfMate")
	if _, err := pool.Exec(context.Background(), `UPDATE candidate_projects SET claimed_start = '2026-01', claimed_end = 'present',
		claimed_team = 'solo' WHERE id = $1::uuid`, proj); err != nil {
		t.Fatal(err)
	}
	setStatus(t, pool, cand, "awaiting_confirmation")

	code, out = roleCall(t, srv.URL, "GET", "/v1/candidates/"+cand+"/found", rec, "recruiter", nil)
	var found struct {
		Projects []struct {
			ClaimedStart string `json:"claimed_start"`
			ClaimedEnd   string `json:"claimed_end"`
			ClaimedTeam  string `json:"claimed_team"`
		}
	}
	if code != 200 || json.Unmarshal([]byte(out), &found) != nil || len(found.Projects) != 1 ||
		found.Projects[0].ClaimedStart != "2026-01" || found.Projects[0].ClaimedEnd != "present" || found.Projects[0].ClaimedTeam != "solo" {
		t.Fatalf("found = %d %s", code, out)
	}

	bad := map[string]any{"projects": []map[string]any{{"id": proj, "name": "ShelfMate", "claimed_start": "Jan 2026"}}}
	if code, out := roleCall(t, srv.URL, "POST", "/v1/candidates/"+cand+"/confirm", rec, "recruiter", bad); code != 400 {
		t.Fatalf("a bad date was accepted: %d %s", code, out)
	}
	good := map[string]any{"projects": []map[string]any{{"id": proj, "name": "ShelfMate", "live_url": "https://example.com",
		"claimed_start": "2025-11", "claimed_end": "2026-02", "claimed_team": "Team", "claimed_team_size": 3, "claimed_role": "backend"}}}
	if code, out := roleCall(t, srv.URL, "POST", "/v1/candidates/"+cand+"/confirm", rec, "recruiter", good); code != 202 {
		t.Fatalf("confirm = %d %s", code, out)
	}
	var start, end, team, role string
	var size int
	if err := pool.QueryRow(context.Background(), `SELECT claimed_start, claimed_end, claimed_team, claimed_team_size, claimed_role
		FROM candidate_projects WHERE id = $1::uuid`, proj).Scan(&start, &end, &team, &size, &role); err != nil {
		t.Fatal(err)
	}
	if start != "2025-11" || end != "2026-02" || team != "team" || size != 3 || role != "backend" {
		t.Errorf("saved %s %s %s %d %s", start, end, team, size, role)
	}
}
