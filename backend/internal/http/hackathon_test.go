package http_test

import (
	"encoding/json"
	"testing"
)

func fixedEventBody() map[string]any {
	b := eventBody()
	b["mode"] = "fixed_problem"
	b["criteria"] = []map[string]any{
		{"name": "Image captioning", "description": "Describes a photo in words", "weight": 3},
		{"name": "History page", "weight": 1},
	}
	return b
}

func makeEvent(t *testing.T, base, email string, body map[string]any) string {
	t.Helper()
	resp, out := call(t, "POST", base+"/v1/events", email, body)
	if resp.StatusCode != 201 {
		t.Fatalf("create event: %d %s", resp.StatusCode, out)
	}
	var e struct {
		ID string `json:"id"`
	}
	_ = json.Unmarshal(out, &e)
	return e.ID
}

func makeProject(t *testing.T, base, email, eventID, team string) string {
	t.Helper()
	resp, out := call(t, "POST", base+"/v1/events/"+eventID+"/projects", email,
		map[string]any{"team_name": team, "live_url": "https://example.com/" + team})
	if resp.StatusCode != 201 {
		t.Fatalf("create project: %d %s", resp.StatusCode, out)
	}
	var p struct {
		ID string `json:"id"`
	}
	_ = json.Unmarshal(out, &p)
	return p.ID
}

func TestFixedProblemEventKeepsItsCriteria(t *testing.T) {
	srv := setup(t)
	id := makeEvent(t, srv.URL, "fixed@example.com", fixedEventBody())
	_, out := call(t, "GET", srv.URL+"/v1/events/"+id, "fixed@example.com", nil)
	var e struct {
		Criteria []struct {
			Name   string  `json:"name"`
			Weight float64 `json:"weight"`
		} `json:"criteria"`
	}
	_ = json.Unmarshal(out, &e)
	if len(e.Criteria) != 2 {
		t.Fatalf("criteria = %s", out)
	}
}

func TestCriteriaRules(t *testing.T) {
	srv := setup(t)
	cases := map[string]func(b map[string]any){
		"fixed problem without criteria": func(b map[string]any) { delete(b, "criteria") },
		"zero weight": func(b map[string]any) {
			b["criteria"] = []map[string]any{{"name": "A", "weight": 0}}
		},
		"no name": func(b map[string]any) {
			b["criteria"] = []map[string]any{{"name": " ", "weight": 1}}
		},
		"same name twice": func(b map[string]any) {
			b["criteria"] = []map[string]any{{"name": "A", "weight": 1}, {"name": "a", "weight": 2}}
		},
		"open theme with criteria": func(b map[string]any) { b["mode"] = "open_theme" },
	}
	for name, change := range cases {
		b := fixedEventBody()
		change(b)
		if resp, out := call(t, "POST", srv.URL+"/v1/events", "crit@example.com", b); resp.StatusCode != 400 {
			t.Errorf("%s: status %d %s, want 400", name, resp.StatusCode, out)
		}
	}
}

func TestProjectsBelongToTheEventOwner(t *testing.T) {
	srv := setup(t)
	eventID := makeEvent(t, srv.URL, "own-a@example.com", eventBody())
	projectID := makeProject(t, srv.URL, "own-a@example.com", eventID, "teamone")

	for _, c := range []struct{ method, path string }{
		{"GET", "/v1/events/" + eventID + "/projects"},
		{"GET", "/v1/projects/" + projectID},
		{"POST", "/v1/projects/" + projectID + "/run"},
		{"POST", "/v1/events/" + eventID + "/run"},
	} {
		if resp, _ := call(t, c.method, srv.URL+c.path, "own-b@example.com", nil); resp.StatusCode != 404 {
			t.Errorf("stranger %s %s got %d, want 404", c.method, c.path, resp.StatusCode)
		}
	}
	if resp, _ := call(t, "POST", srv.URL+"/v1/events/"+eventID+"/projects", "own-b@example.com",
		map[string]any{"team_name": "x", "live_url": "https://example.com"}); resp.StatusCode != 404 {
		t.Errorf("stranger adding a project got %d, want 404", resp.StatusCode)
	}

	_, out := call(t, "GET", srv.URL+"/v1/events/"+eventID+"/projects", "own-a@example.com", nil)
	var list []map[string]any
	_ = json.Unmarshal(out, &list)
	if len(list) != 1 || list[0]["status"] != "submitted" {
		t.Errorf("list = %s", out)
	}
}

func TestProjectValidation(t *testing.T) {
	srv := setup(t)
	eventID := makeEvent(t, srv.URL, "val@example.com", eventBody())
	for name, body := range map[string]map[string]any{
		"no team name":      {"live_url": "https://example.com"},
		"no links":          {"team_name": "t"},
		"not a web address": {"team_name": "t", "repo_url": "github.com/a/b"},
		"unknown field":     {"team_name": "t", "live_url": "https://example.com", "score": 10},
	} {
		if resp, out := call(t, "POST", srv.URL+"/v1/events/"+eventID+"/projects", "val@example.com", body); resp.StatusCode != 400 {
			t.Errorf("%s: status %d %s, want 400", name, resp.StatusCode, out)
		}
	}
	// A repo-only project is fine: it gets the sandbox track later.
	if resp, out := call(t, "POST", srv.URL+"/v1/events/"+eventID+"/projects", "val@example.com",
		map[string]any{"team_name": "repo only", "repo_url": "https://github.com/a/b"}); resp.StatusCode != 201 {
		t.Errorf("repo only: %d %s", resp.StatusCode, out)
	}
}

func TestStartAndRerunAProject(t *testing.T) {
	srv := setup(t)
	eventID := makeEvent(t, srv.URL, "run@example.com", eventBody())
	one := makeProject(t, srv.URL, "run@example.com", eventID, "one")
	two := makeProject(t, srv.URL, "run@example.com", eventID, "two")

	resp, out := call(t, "POST", srv.URL+"/v1/projects/"+one+"/run", "run@example.com", nil)
	if resp.StatusCode != 202 {
		t.Fatalf("start: %d %s", resp.StatusCode, out)
	}
	// The first stage is still waiting, so a second press must not start a second check.
	if resp, _ := call(t, "POST", srv.URL+"/v1/projects/"+one+"/run", "run@example.com", nil); resp.StatusCode != 409 {
		t.Errorf("second start while running: %d, want 409", resp.StatusCode)
	}

	// Starting the event checks only the project that has not been checked yet.
	resp, out = call(t, "POST", srv.URL+"/v1/events/"+eventID+"/run", "run@example.com", nil)
	if resp.StatusCode != 202 {
		t.Fatalf("start event: %d %s", resp.StatusCode, out)
	}
	var r struct {
		Started []string `json:"started"`
		Skipped []string `json:"skipped"`
	}
	_ = json.Unmarshal(out, &r)
	if len(r.Started) != 1 || r.Started[0] != two || len(r.Skipped) != 1 || r.Skipped[0] != one {
		t.Errorf("started %v skipped %v", r.Started, r.Skipped)
	}
}
