package http_test

import (
	"bytes"
	"encoding/json"
	"io"
	"log/slog"
	nethttp "net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	apihttp "github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/http"
)

const secret = "0123456789abcdef0123"

func setup(t *testing.T) *httptest.Server {
	t.Helper()
	pool := dbtest.Pool(t)
	h := apihttp.NewHandler(apihttp.Options{
		Pool: pool, AuthSecret: secret, WebOrigin: "http://localhost:3000",
		EnableDevEndpoints: true, Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
	})
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return srv
}

func call(t *testing.T, method, url, email string, body any) (*nethttp.Response, []byte) {
	t.Helper()
	var rd io.Reader
	if body != nil {
		raw, _ := json.Marshal(body)
		rd = bytes.NewReader(raw)
	}
	req, _ := nethttp.NewRequest(method, url, rd)
	if email != "" {
		tok, _ := auth.Sign(secret, email, "", time.Minute)
		req.Header.Set("Authorization", "Bearer "+tok)
	}
	resp, err := nethttp.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	return resp, out
}

func eventBody() map[string]any {
	return map[string]any{
		"name": "Test Hack", "mode": "open_theme",
		"starts_at": "2026-11-01T09:00:00Z", "ends_at": "2026-11-02T09:00:00Z",
	}
}

func TestHealthNeedsNoSignIn(t *testing.T) {
	srv := setup(t)
	resp, _ := call(t, "GET", srv.URL+"/healthz", "", nil)
	if resp.StatusCode != 200 {
		t.Fatalf("status %d", resp.StatusCode)
	}
}

func TestPrivateRoutesNeedSignIn(t *testing.T) {
	srv := setup(t)
	for _, path := range []string{"/v1/me", "/v1/events", "/v1/candidates"} {
		resp, _ := call(t, "GET", srv.URL+path, "", nil)
		if resp.StatusCode != 401 {
			t.Errorf("%s without a token: status %d, want 401", path, resp.StatusCode)
		}
	}
}

func TestOnlyTheOwnerCanSeeAnEvent(t *testing.T) {
	srv := setup(t)
	resp, out := call(t, "POST", srv.URL+"/v1/events", "owner-a@example.com", eventBody())
	if resp.StatusCode != 201 {
		t.Fatalf("create: %d %s", resp.StatusCode, out)
	}
	var created struct {
		ID        string `json:"id"`
		RoleLevel string `json:"role_level"`
	}
	_ = json.Unmarshal(out, &created)
	if created.RoleLevel != "fresher" {
		t.Errorf("default role level = %q, want fresher", created.RoleLevel)
	}

	if resp, _ := call(t, "GET", srv.URL+"/v1/events/"+created.ID, "owner-a@example.com", nil); resp.StatusCode != 200 {
		t.Errorf("owner got %d", resp.StatusCode)
	}
	// Someone else gets "not found", the same answer as for an event that does not exist.
	if resp, _ := call(t, "GET", srv.URL+"/v1/events/"+created.ID, "owner-b@example.com", nil); resp.StatusCode != 404 {
		t.Errorf("stranger got %d, want 404", resp.StatusCode)
	}
	if resp, _ := call(t, "GET", srv.URL+"/v1/events/not-a-uuid", "owner-a@example.com", nil); resp.StatusCode != 404 {
		t.Errorf("malformed id got %d, want 404", resp.StatusCode)
	}

	_, listB := call(t, "GET", srv.URL+"/v1/events", "owner-b@example.com", nil)
	var events []map[string]any
	_ = json.Unmarshal(listB, &events)
	for _, e := range events {
		if e["id"] == created.ID {
			t.Error("another owner's event appears in the list")
		}
	}
}

func TestEventValidation(t *testing.T) {
	srv := setup(t)
	bad := eventBody()
	bad["mode"] = "nonsense"
	if resp, _ := call(t, "POST", srv.URL+"/v1/events", "v@example.com", bad); resp.StatusCode != 400 {
		t.Errorf("bad mode: %d", resp.StatusCode)
	}
	bad = eventBody()
	bad["role_level"] = "wizard"
	if resp, _ := call(t, "POST", srv.URL+"/v1/events", "v@example.com", bad); resp.StatusCode != 400 {
		t.Errorf("bad role level: %d", resp.StatusCode)
	}
	bad = eventBody()
	bad["ends_at"] = "2026-10-01T09:00:00Z"
	if resp, _ := call(t, "POST", srv.URL+"/v1/events", "v@example.com", bad); resp.StatusCode != 400 {
		t.Errorf("end before start: %d", resp.StatusCode)
	}
	bad = eventBody()
	bad["unknown_field"] = 1
	if resp, _ := call(t, "POST", srv.URL+"/v1/events", "v@example.com", bad); resp.StatusCode != 400 {
		t.Errorf("unknown field: %d", resp.StatusCode)
	}
}

func TestCandidateCreateAndOwnership(t *testing.T) {
	srv := setup(t)
	resp, out := call(t, "POST", srv.URL+"/v1/candidates", "r1@example.com", map[string]any{
		"label": "Asha", "role_level": "junior",
		"coding_handles": map[string]string{"codeforces": "asha_cf"},
	})
	if resp.StatusCode != 201 {
		t.Fatalf("create: %d %s", resp.StatusCode, out)
	}
	var c struct {
		ID            string            `json:"id"`
		CodingHandles map[string]string `json:"coding_handles"`
	}
	_ = json.Unmarshal(out, &c)
	if c.CodingHandles["codeforces"] != "asha_cf" {
		t.Errorf("handles = %v", c.CodingHandles)
	}
	if resp, _ := call(t, "GET", srv.URL+"/v1/candidates/"+c.ID, "r2@example.com", nil); resp.StatusCode != 404 {
		t.Errorf("stranger got %d, want 404", resp.StatusCode)
	}
	if resp, _ := call(t, "POST", srv.URL+"/v1/candidates", "r1@example.com", map[string]any{
		"coding_handles": map[string]string{"hackerrank": "x"}}); resp.StatusCode != 400 {
		t.Errorf("unknown site: %d", resp.StatusCode)
	}
}

func TestSelfTestEndpointStartsAPipeline(t *testing.T) {
	srv := setup(t)
	resp, out := call(t, "POST", srv.URL+"/v1/dev/selftest", "dev@example.com", nil)
	if resp.StatusCode != 202 {
		t.Fatalf("status %d %s", resp.StatusCode, out)
	}
	var started struct {
		Target string   `json:"target"`
		Jobs   []string `json:"started_jobs"`
	}
	_ = json.Unmarshal(out, &started)
	if started.Target == "" || len(started.Jobs) != 1 {
		t.Fatalf("got %s", out)
	}
	_, status := call(t, "GET", srv.URL+"/v1/dev/selftest/"+started.Target, "dev@example.com", nil)
	if !bytes.Contains(status, []byte("selftest_a")) {
		t.Errorf("status = %s", status)
	}
}
