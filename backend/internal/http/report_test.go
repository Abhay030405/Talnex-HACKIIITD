package http_test

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	apihttp "github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/http"
)

type fakeLinks struct{ fail bool }

func (f fakeLinks) ViewLink(_ context.Context, key string) (string, error) {
	if f.fail {
		return "", errors.New("storage down")
	}
	return "https://files.example/view/" + key + "?sig=abc", nil
}

const sampleReport = `{"version":1,"candidate_id":"x","has_gaps":false,"projects":[
 {"name":"TinyTools","features":[
  {"text":"converts units","proof":[
    {"step":1,"action":"open","observed":"home","proof_key":"screens/p/r/1"},
    {"step":2,"action":"type","observed":"no screenshot"}]},
  {"text":"no proof at all"}]}],
 "coding_signals":[],"flags":[],"notes":[]}`

func setupReport(t *testing.T, links apihttp.ProofLinks) *httptest.Server {
	t.Helper()
	h := apihttp.NewHandler(apihttp.Options{
		Pool: dbtest.Pool(t), AuthSecret: secret, WebOrigin: "http://localhost:3000",
		ProofLinks: links, Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
	})
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return srv
}

func saveReport(t *testing.T, candidate string, hasGaps bool) {
	t.Helper()
	_, err := dbtest.Pool(t).Exec(context.Background(), `
		INSERT INTO candidate_reports (candidate_id, report, has_gaps) VALUES ($1::uuid, $2::jsonb, $3)
		ON CONFLICT (candidate_id) DO UPDATE SET report = EXCLUDED.report, has_gaps = EXCLUDED.has_gaps`,
		candidate, sampleReport, hasGaps)
	if err != nil {
		t.Fatal(err)
	}
}

func TestReportSwapsStorageKeysForViewLinks(t *testing.T) {
	srv := setupReport(t, fakeLinks{})
	id := makeCandidate(t, srv.URL, "rep1@example.com")

	if resp, out := call(t, "GET", srv.URL+"/v1/candidates/"+id+"/report", "rep1@example.com", nil); resp.StatusCode != 404 ||
		!strings.Contains(string(out), "not ready") {
		t.Fatalf("before the report exists: %d %s", resp.StatusCode, out)
	}

	saveReport(t, id, true)
	resp, out := call(t, "GET", srv.URL+"/v1/candidates/"+id+"/report", "rep1@example.com", nil)
	if resp.StatusCode != 200 {
		t.Fatalf("report: %d %s", resp.StatusCode, out)
	}
	if strings.Contains(string(out), "proof_key") || strings.Contains(string(out), "screens/p/r/1\"") {
		t.Errorf("a raw storage key left the server: %s", out)
	}
	var got struct {
		HasGaps  bool `json:"has_gaps"`
		Projects []struct {
			Features []struct {
				Proof []map[string]any `json:"proof"`
			} `json:"features"`
		} `json:"projects"`
	}
	if err := json.Unmarshal(out, &got); err != nil {
		t.Fatal(err)
	}
	if !got.HasGaps {
		t.Error("has_gaps should come from the saved row")
	}
	steps := got.Projects[0].Features[0].Proof
	if steps[0]["proof_url"] != "https://files.example/view/screens/p/r/1?sig=abc" {
		t.Errorf("first step link = %v", steps[0]["proof_url"])
	}
	if _, has := steps[1]["proof_url"]; has {
		t.Errorf("a step without a screenshot got a link: %v", steps[1])
	}
}

func TestReportWithoutLinkMakerOrWithBrokenStorageStillHidesKeys(t *testing.T) {
	for name, links := range map[string]apihttp.ProofLinks{"nil": nil, "failing": fakeLinks{fail: true}} {
		t.Run(name, func(t *testing.T) {
			srv := setupReport(t, links)
			id := makeCandidate(t, srv.URL, "rep2-"+name+"@example.com")
			saveReport(t, id, false)
			resp, out := call(t, "GET", srv.URL+"/v1/candidates/"+id+"/report", "rep2-"+name+"@example.com", nil)
			if resp.StatusCode != 200 {
				t.Fatalf("%d %s", resp.StatusCode, out)
			}
			if strings.Contains(string(out), "proof_key") || strings.Contains(string(out), "proof_url") || strings.Contains(string(out), "screens/") {
				t.Errorf("keys or links present: %s", out)
			}
		})
	}
}

func TestReportIsPrivateToTheOwner(t *testing.T) {
	srv := setupReport(t, fakeLinks{})
	id := makeCandidate(t, srv.URL, "rep3@example.com")
	saveReport(t, id, false)
	url := srv.URL + "/v1/candidates/" + id + "/report"
	if resp, _ := call(t, "GET", url, "rep3-stranger@example.com", nil); resp.StatusCode != 404 {
		t.Errorf("stranger got %d, want 404", resp.StatusCode)
	}
	if resp, _ := call(t, "GET", url, "", nil); resp.StatusCode != 401 {
		t.Errorf("anonymous got %d, want 401", resp.StatusCode)
	}
	if resp, _ := call(t, "GET", srv.URL+"/v1/candidates/not-a-uuid/report", "rep3@example.com", nil); resp.StatusCode != 404 {
		t.Errorf("bad id got %d, want 404", resp.StatusCode)
	}
}
