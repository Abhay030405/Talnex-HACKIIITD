package api_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd/api"
)

const token = "test-token-0123456789"

// quietDriver is a driver that does nothing but answer. Exec echoes the command it was given.
type quietDriver struct{ created map[string]bool }

func (d *quietDriver) Ping(context.Context) error { return nil }
func (d *quietDriver) Create(_ context.Context, id string, _ sandboxd.VMSpec) error {
	d.created[id] = true
	return nil
}
func (d *quietDriver) CopyIn(_ context.Context, _, dir string, r io.Reader) error {
	_, _ = io.Copy(io.Discard, r)
	return nil
}
func (d *quietDriver) Exec(_ context.Context, _ string, spec sandboxd.ExecSpec) (sandboxd.ExecResult, error) {
	return sandboxd.ExecResult{Stdout: strings.Join(spec.Command, " ")}, nil
}
func (d *quietDriver) Destroy(_ context.Context, id string) error { delete(d.created, id); return nil }
func (d *quietDriver) List(context.Context) ([]string, error)     { return nil, nil }

func setup(t *testing.T, maxVMs int) *httptest.Server {
	t.Helper()
	m := sandboxd.NewManager(&quietDriver{created: map[string]bool{}},
		sandboxd.Limits{MaxVMs: maxVMs, CPUs: 2, MemoryMB: 512, TimeLimit: time.Minute, ExecTimeout: time.Minute})
	srv := httptest.NewServer(api.NewHandler(m, "docker", token, slog.New(slog.NewTextHandler(io.Discard, nil))))
	t.Cleanup(srv.Close)
	return srv
}

func call(t *testing.T, method, url, tok string, body any) (*http.Response, []byte) {
	t.Helper()
	var rd io.Reader
	if body != nil {
		raw, _ := json.Marshal(body)
		rd = bytes.NewReader(raw)
	}
	req, _ := http.NewRequest(method, url, rd)
	if tok != "" {
		req.Header.Set("Authorization", "Bearer "+tok)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	return resp, out
}

func TestHealthNeedsNoTokenButEverythingElseDoes(t *testing.T) {
	srv := setup(t, 2)
	if resp, _ := call(t, "GET", srv.URL+"/healthz", "", nil); resp.StatusCode != 200 {
		t.Errorf("healthz: %d", resp.StatusCode)
	}
	for _, tok := range []string{"", "wrong", token + "x"} {
		if resp, _ := call(t, "GET", srv.URL+"/v1/vms", tok, nil); resp.StatusCode != 401 {
			t.Errorf("token %q: %d, want 401", tok, resp.StatusCode)
		}
	}
	if resp, _ := call(t, "GET", srv.URL+"/v1/vms", token, nil); resp.StatusCode != 200 {
		t.Errorf("right token: %d", resp.StatusCode)
	}
}

func TestACreateExecUploadDestroyRound(t *testing.T) {
	srv := setup(t, 2)
	resp, out := call(t, "POST", srv.URL+"/v1/vms", token, map[string]any{"image": "talnex-sandbox-node"})
	if resp.StatusCode != 201 {
		t.Fatalf("create: %d %s", resp.StatusCode, out)
	}
	var vm struct{ ID string }
	_ = json.Unmarshal(out, &vm)

	resp, out = call(t, "POST", srv.URL+"/v1/vms/"+vm.ID+"/exec", token, map[string]any{"command": "echo hi && ls"})
	if resp.StatusCode != 200 || !strings.Contains(string(out), "sh -c echo hi \\u0026\\u0026 ls") && !strings.Contains(string(out), "echo hi") {
		t.Errorf("exec: %d %s", resp.StatusCode, out)
	}

	req, _ := http.NewRequest("POST", srv.URL+"/v1/vms/"+vm.ID+"/files?dir=/work/app", strings.NewReader("tar bytes"))
	req.Header.Set("Authorization", "Bearer "+token)
	up, err := http.DefaultClient.Do(req)
	if err != nil || up.StatusCode != 204 {
		t.Errorf("upload: %v %v", err, up)
	}

	if resp, _ := call(t, "DELETE", srv.URL+"/v1/vms/"+vm.ID, token, nil); resp.StatusCode != 204 {
		t.Errorf("destroy: %d", resp.StatusCode)
	}
	if resp, _ := call(t, "POST", srv.URL+"/v1/vms/"+vm.ID+"/exec", token, map[string]any{"command": "ls"}); resp.StatusCode != 404 {
		t.Errorf("exec on a destroyed VM: %d, want 404", resp.StatusCode)
	}
	if resp, _ := call(t, "DELETE", srv.URL+"/v1/vms/"+vm.ID, token, nil); resp.StatusCode != 204 {
		t.Errorf("destroying twice: %d, want 204", resp.StatusCode)
	}
}

func TestBadCallsGetPlainAnswers(t *testing.T) {
	srv := setup(t, 1)
	if resp, _ := call(t, "POST", srv.URL+"/v1/vms", token, map[string]any{"image": "ubuntu"}); resp.StatusCode != 400 {
		t.Errorf("foreign image: %d", resp.StatusCode)
	}
	if resp, _ := call(t, "POST", srv.URL+"/v1/vms", token, map[string]any{"image": "talnex-sandbox-node", "surprise": 1}); resp.StatusCode != 400 {
		t.Errorf("unknown field: %d", resp.StatusCode)
	}
	if resp, _ := call(t, "POST", srv.URL+"/v1/vms/nope/exec", token, map[string]any{"command": "ls"}); resp.StatusCode != 404 {
		t.Errorf("unknown VM: %d", resp.StatusCode)
	}
	call(t, "POST", srv.URL+"/v1/vms", token, map[string]any{"image": "talnex-sandbox-node"})
	resp, _ := call(t, "POST", srv.URL+"/v1/vms", token, map[string]any{"image": "talnex-sandbox-node"})
	if resp.StatusCode != 429 || resp.Header.Get("Retry-After") == "" {
		t.Errorf("host full: %d retry-after %q", resp.StatusCode, resp.Header.Get("Retry-After"))
	}
}
