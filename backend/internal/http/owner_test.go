package http_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	nethttp "net/http"
	"net/http/httptest"
	"os"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	apihttp "github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/http"
)

// roleCall sends a request signed in with an explicit role ("" for no token).
func roleCall(t *testing.T, base, method, path, email, role string, body any) (int, string) {
	t.Helper()
	var rd io.Reader
	if body != nil {
		raw, _ := json.Marshal(body)
		rd = bytes.NewReader(raw)
	}
	req, _ := nethttp.NewRequest(method, base+path, rd)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if email != "" {
		tok, err := auth.SignWithRole(secret, email, "", role, time.Minute)
		if err != nil {
			t.Fatal(err)
		}
		req.Header.Set("Authorization", "Bearer "+tok)
	}
	resp, err := nethttp.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, string(out)
}

func idOf(t *testing.T, code int, out string) string {
	t.Helper()
	if code != 201 {
		t.Fatalf("create: %d %s", code, out)
	}
	var v struct {
		ID string `json:"id"`
	}
	_ = json.Unmarshal([]byte(out), &v)
	return v.ID
}

// ownerRoutes is every private route in server.go (the dev routes are left out on purpose).
// "scoped" routes name one object of the owner; the others are checked for sign-in, role and not leaking lists.
var ownerRoutes = []struct {
	method, path, role string
	scoped             bool
}{
	{"GET", "/v1/me", "", false},
	{"POST", "/v1/events", "organizer", false},
	{"GET", "/v1/events", "organizer", false},
	{"GET", "/v1/events/{event}", "organizer", true},
	{"POST", "/v1/events/{event}/projects", "organizer", true},
	{"GET", "/v1/events/{event}/projects", "organizer", true},
	{"POST", "/v1/events/{event}/run", "organizer", true},
	{"GET", "/v1/projects/{project}", "organizer", true},
	{"GET", "/v1/projects/{project}/proof", "organizer", true},
	{"GET", "/v1/events/{event}/overview", "organizer", true},
	{"GET", "/v1/events/{event}/compare", "organizer", true},
	{"POST", "/v1/projects/{project}/run", "organizer", true},
	{"PUT", "/v1/events/{event}/criteria", "organizer", true},
	{"POST", "/v1/projects/{project}/ask", "organizer", true},
	{"GET", "/v1/projects/{project}/asks", "organizer", true},
	{"POST", "/v1/roles", "recruiter", false},
	{"GET", "/v1/roles", "recruiter", false},
	{"GET", "/v1/roles/{role}", "recruiter", true},
	{"PUT", "/v1/roles/{role}", "recruiter", true},
	{"POST", "/v1/candidates", "recruiter", false},
	{"GET", "/v1/candidates", "recruiter", false},
	{"GET", "/v1/candidates/{cand}", "recruiter", true},
	{"POST", "/v1/candidates/{cand}/resume", "recruiter", true},
	{"GET", "/v1/candidates/{cand}/report", "recruiter", true},
	{"GET", "/v1/candidates/{cand}/progress", "recruiter", true},
	{"GET", "/v1/candidates/{cand}/found", "recruiter", true},
	{"POST", "/v1/candidates/{cand}/confirm", "recruiter", true},
	{"POST", "/v1/candidates/{cand}/rerun-coding", "recruiter", true},
	{"POST", "/v1/candidates/{cand}/ask", "recruiter", true},
	{"GET", "/v1/candidates/{cand}/asks", "recruiter", true},
	{"POST", "/v1/candidate-projects/{cproj}/rerun", "recruiter", true},
	{"POST", "/v1/candidate-projects/{cproj}/custom-test", "recruiter", true},
	{"GET", "/v1/candidate-projects/{cproj}/custom-tests", "recruiter", true},
	{"POST", "/v1/projects/{project}/custom-test", "organizer", true},
	{"GET", "/v1/projects/{project}/custom-tests", "organizer", true},
	{"DELETE", "/v1/candidates/{cand}", "recruiter", true},
	{"POST", "/v1/projects/{project}/walkthroughs", "organizer", true},
	{"GET", "/v1/projects/{project}/walkthroughs", "organizer", true},
	{"POST", "/v1/candidate-projects/{cproj}/walkthroughs", "recruiter", true},
	{"GET", "/v1/candidate-projects/{cproj}/walkthroughs", "recruiter", true},
	{"GET", "/v1/walkthroughs/{walk}", "", true},
	{"GET", "/v1/live/{kind}/{event}", "", true},
}

func TestEveryPrivateRouteChecksTheOwner(t *testing.T) {
	// 1. The table must list every private route that server.go registers.
	src, err := os.ReadFile("server.go")
	if err != nil {
		t.Fatal(err)
	}
	re := regexp.MustCompile(`private\.HandleFunc\("([A-Z]+) (/v1/[^"]*)"`)
	registered := map[string]bool{}
	for _, m := range re.FindAllStringSubmatch(string(src), -1) {
		if strings.HasPrefix(m[2], "/v1/dev/") {
			continue
		}
		registered[m[1]+" "+regexp.MustCompile(`\{[a-z]+\}`).ReplaceAllString(m[2], "{id}")] = true
	}
	listed := map[string]bool{}
	for _, r := range ownerRoutes {
		listed[r.method+" "+regexp.MustCompile(`\{[a-z]+\}`).ReplaceAllString(r.path, "{id}")] = true
	}
	for k := range registered {
		if !listed[k] {
			t.Errorf("route %q is registered in server.go but missing from the owner audit table", k)
		}
	}
	for k := range listed {
		if !registered[k] {
			t.Errorf("route %q is in the audit table but not registered in server.go", k)
		}
	}

	// 2. Real objects made by their owners.
	pool := dbtest.Pool(t)
	h := apihttp.NewHandler(apihttp.Options{
		Pool: pool, AuthSecret: secret, WebOrigin: "http://localhost:3000",
		Files: &fakeFiles{saved: map[string][]byte{}}, ProofLinks: fakeLinks{},
		Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
	})
	srv := httptest.NewServer(h)
	defer srv.Close()

	run := uuid.NewString()[:8]
	org, orgStranger := "audit-org-"+run+"@example.com", "audit-org2-"+run+"@example.com"
	rec, recStranger := "audit-rec-"+run+"@example.com", "audit-rec2-"+run+"@example.com"

	code, out := roleCall(t, srv.URL, "POST", "/v1/events", org, "organizer", eventBody())
	eventID := idOf(t, code, out)
	code, out = roleCall(t, srv.URL, "POST", "/v1/events/"+eventID+"/projects", org, "organizer",
		map[string]any{"team_name": "t", "live_url": "https://example.com"})
	projectID := idOf(t, code, out)
	code, out = roleCall(t, srv.URL, "POST", "/v1/roles", rec, "recruiter", map[string]any{"title": "Audit role"})
	roleID := idOf(t, code, out)
	code, out = roleCall(t, srv.URL, "POST", "/v1/candidates", rec, "recruiter", map[string]any{"label": "Asha"})
	candID := idOf(t, code, out)
	if _, err := pool.Exec(context.Background(),
		`INSERT INTO candidate_reports (candidate_id, report) VALUES ($1::uuid, '{"projects":[]}')`, candID); err != nil {
		t.Fatal(err)
	}
	var cprojID string
	if err := pool.QueryRow(context.Background(),
		`INSERT INTO candidate_projects (candidate_id, name) VALUES ($1::uuid, 'Shelf') RETURNING id::text`, candID).Scan(&cprojID); err != nil {
		t.Fatal(err)
	}
	code, out = roleCall(t, srv.URL, "POST", "/v1/projects/"+projectID+"/walkthroughs", org, "organizer", map[string]any{"question": "how?"})
	if code != 202 {
		t.Fatalf("ask: %d %s", code, out)
	}
	var walk struct {
		ID string `json:"id"`
	}
	_ = json.Unmarshal([]byte(out), &walk)
	// Make the two strangers real accounts with the right role.
	roleCall(t, srv.URL, "GET", "/v1/me", orgStranger, "organizer", nil)
	roleCall(t, srv.URL, "GET", "/v1/me", recStranger, "recruiter", nil)

	fill := strings.NewReplacer("{event}", eventID, "{project}", projectID, "{cand}", candID, "{cproj}", cprojID, "{walk}", walk.ID, "{kind}", "event", "{role}", roleID)
	for _, r := range ownerRoutes {
		path := fill.Replace(r.path)
		name := r.method + " " + r.path
		stranger, strangerRole := orgStranger, "organizer"
		wrongRole := "recruiter"
		if r.role == "recruiter" {
			stranger, strangerRole = recStranger, "recruiter"
			wrongRole = "organizer"
		}

		// Anonymous: 401.
		if code, out := roleCall(t, srv.URL, r.method, path, "", "", nil); code != 401 {
			t.Errorf("%s anonymous: %d %s, want 401", name, code, out)
		}
		// Signed in with the other kind of account: 403.
		if r.role != "" {
			other := "audit-wrong-" + run + "-" + wrongRole + "@example.com"
			if code, out := roleCall(t, srv.URL, r.method, path, other, wrongRole, nil); code != 403 {
				t.Errorf("%s wrong role: %d %s, want 403", name, code, out)
			}
		}
		// A stranger with the right role: 404 on someone else's object.
		if r.scoped {
			code, out := roleCall(t, srv.URL, r.method, path, stranger, strangerRole, nil)
			if code != 404 {
				t.Errorf("%s stranger: %d %s, want 404", name, code, out)
			}
			for _, secretPart := range []string{eventID, projectID, candID, "Asha", "example.com"} {
				if strings.Contains(out, secretPart) {
					t.Errorf("%s stranger response leaks %q: %s", name, secretPart, out)
				}
			}
		}
	}

	// Lists show only your own things.
	for path, role := range map[string]string{"/v1/events": "organizer", "/v1/candidates": "recruiter"} {
		stranger := orgStranger
		if role == "recruiter" {
			stranger = recStranger
		}
		code, out := roleCall(t, srv.URL, "GET", path, stranger, role, nil)
		if code != 200 || strings.TrimSpace(out) != "[]" {
			t.Errorf("stranger %s: %d %s, want an empty list", path, code, out)
		}
	}

	// The owner still gets everything (so the 404s above are not a broken route).
	for _, p := range []struct{ path, role, who string }{
		{"/v1/events/" + eventID, "organizer", org},
		{"/v1/projects/" + projectID, "organizer", org},
		{"/v1/candidates/" + candID, "recruiter", rec},
		{"/v1/candidates/" + candID + "/report", "recruiter", rec},
		{"/v1/candidate-projects/" + cprojID + "/walkthroughs", "recruiter", rec},
		{"/v1/walkthroughs/" + walk.ID, "organizer", org},
	} {
		if code, out := roleCall(t, srv.URL, "GET", p.path, p.who, p.role, nil); code != 200 {
			t.Errorf("owner GET %s: %d %s, want 200", p.path, code, out)
		}
	}
}
