package drivers_test

import (
	"archive/tar"
	"bytes"
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd/drivers"
)

// These tests use the real Docker engine and the image talnex-sandbox-full (bash sandbox/host/build_images.sh).
// They are skipped unless TALNEX_TEST_DOCKER=1, so `go test ./...` works on a machine without Docker.

const tinyApp = `const http = require('http');
http.createServer((req, res) => {
  if (req.url === '/boom') { res.statusCode = 500; res.end('boom'); return; }
  let body = '';
  req.on('data', c => body += c);
  req.on('end', () => {
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ method: req.method, url: req.url, got: body }));
  });
}).listen(3000);
`

func archiveOf(t *testing.T, files map[string]string) *bytes.Reader {
	t.Helper()
	var buf bytes.Buffer
	tw := tar.NewWriter(&buf)
	for name, content := range files {
		if err := tw.WriteHeader(&tar.Header{Name: name, Mode: 0o644, Size: int64(len(content))}); err != nil {
			t.Fatal(err)
		}
		_, _ = tw.Write([]byte(content))
	}
	_ = tw.Close()
	return bytes.NewReader(buf.Bytes())
}

func TestARealVMRunsAnAppThatWeUploadAndTalkTo(t *testing.T) {
	if os.Getenv("TALNEX_TEST_DOCKER") != "1" {
		t.Skip("TALNEX_TEST_DOCKER is not 1")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()
	m := sandboxd.NewManager(drivers.NewDocker(), sandboxd.Limits{MaxVMs: 2, CPUs: 1, MemoryMB: 512, TimeLimit: 3 * time.Minute, ExecTimeout: time.Minute})
	if err := m.Ping(ctx); err != nil {
		t.Fatalf("docker is not answering: %v", err)
	}
	vm, err := m.Create(ctx, sandboxd.CreateRequest{Image: "talnex-sandbox-full"})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = m.Destroy(context.Background(), vm.ID) })

	if err := m.Upload(ctx, vm.ID, "/work/app", archiveOf(t, map[string]string{"server.js": tinyApp})); err != nil {
		t.Fatal(err)
	}
	res, err := m.Exec(ctx, vm.ID, sandboxd.ExecSpec{Command: []string{"sh", "-c", "ls /work/app && node --version"}, Timeout: 20 * time.Second})
	if err != nil || res.ExitCode != 0 || !strings.Contains(res.Stdout, "server.js") {
		t.Fatalf("ls: %+v %v", res, err)
	}

	// A failing command is a result with its exit code and the error text, not an error of the host.
	if res, err := m.Exec(ctx, vm.ID, sandboxd.ExecSpec{Command: []string{"sh", "-c", "echo oops >&2; exit 3"}, Timeout: 10 * time.Second}); err != nil || res.ExitCode != 3 || !strings.Contains(res.Stderr, "oops") {
		t.Errorf("failing command: %+v %v", res, err)
	}
	// A command that runs too long is stopped inside the VM and reported as timed out.
	if res, err := m.Exec(ctx, vm.ID, sandboxd.ExecSpec{Command: []string{"sleep", "30"}, Timeout: 2 * time.Second}); err != nil || !res.TimedOut {
		t.Errorf("sleep: %+v %v", res, err)
	}

	// Start the app in the background, wait for the port, then talk to it.
	if _, err := m.Exec(ctx, vm.ID, sandboxd.ExecSpec{Command: []string{"sh", "-c", "node server.js > /tmp/app.log 2>&1"}, WorkDir: "/work/app", Detach: true}); err != nil {
		t.Fatal(err)
	}
	var ports []int
	for i := 0; i < 20 && len(ports) == 0; i++ {
		time.Sleep(500 * time.Millisecond)
		if ports, err = m.ListeningPorts(ctx, vm.ID); err != nil {
			t.Fatal(err)
		}
	}
	if len(ports) != 1 || ports[0] != 3000 {
		t.Fatalf("ports = %v, want [3000]", ports)
	}

	got, err := m.Request(ctx, vm.ID, sandboxd.HTTPRequest{Method: "POST", Port: 3000, Path: "/items?x=1", Headers: map[string]string{"Content-Type": "application/json"}, Body: []byte(`{"name":"a"}`)})
	if err != nil || got.Status != 200 || !strings.Contains(string(got.Body), `"method":"POST"`) || !strings.Contains(string(got.Body), `{\"name\":\"a\"}`) {
		t.Fatalf("POST: %+v %v", got, err)
	}
	if got, _ := m.Request(ctx, vm.ID, sandboxd.HTTPRequest{Port: 3000, Path: "/boom"}); got.Status != 500 || string(got.Body) != "boom" {
		t.Errorf("a 500 is an answer, not an error: %+v", got)
	}
	if got, _ := m.Request(ctx, vm.ID, sandboxd.HTTPRequest{Port: 9999, Path: "/"}); got.Status != 0 || !strings.Contains(got.Error, "connection refused") {
		t.Errorf("nothing listening: %+v", got)
	}

	if err := m.Destroy(ctx, vm.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := m.Exec(ctx, vm.ID, sandboxd.ExecSpec{Command: []string{"ls"}}); err == nil {
		t.Error("the VM should be gone")
	}
}
