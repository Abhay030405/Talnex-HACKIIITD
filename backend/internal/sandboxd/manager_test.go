package sandboxd_test

import (
	"context"
	"errors"
	"io"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd"
)

// fakeDriver stands in for docker. Exec answers from a script and remembers what it was asked.
type fakeDriver struct {
	mu        sync.Mutex
	created   map[string]sandboxd.VMSpec
	destroyed []string
	execs     []sandboxd.ExecSpec
	reply     func(spec sandboxd.ExecSpec) sandboxd.ExecResult
	failNext  error
}

func newFake() *fakeDriver { return &fakeDriver{created: map[string]sandboxd.VMSpec{}} }

func (f *fakeDriver) Ping(context.Context) error { return nil }
func (f *fakeDriver) Create(_ context.Context, id string, spec sandboxd.VMSpec) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failNext != nil {
		err := f.failNext
		f.failNext = nil
		return err
	}
	f.created[id] = spec
	return nil
}
func (f *fakeDriver) CopyIn(context.Context, string, string, io.Reader) error { return nil }
func (f *fakeDriver) Exec(_ context.Context, _ string, spec sandboxd.ExecSpec) (sandboxd.ExecResult, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.execs = append(f.execs, spec)
	if f.reply != nil {
		return f.reply(spec), nil
	}
	return sandboxd.ExecResult{}, nil
}
func (f *fakeDriver) Destroy(_ context.Context, id string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.destroyed = append(f.destroyed, id)
	delete(f.created, id)
	return nil
}
func (f *fakeDriver) List(context.Context) ([]string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	var ids []string
	for id := range f.created {
		ids = append(ids, id)
	}
	return ids, nil
}

var limits = sandboxd.Limits{MaxVMs: 2, CPUs: 2, MemoryMB: 1024, TimeLimit: 10 * time.Minute, ExecTimeout: 5 * time.Minute}

func newVM(t *testing.T, m *sandboxd.Manager) sandboxd.VM {
	t.Helper()
	vm, err := m.Create(context.Background(), sandboxd.CreateRequest{Image: "talnex-sandbox-node"})
	if err != nil {
		t.Fatal(err)
	}
	return vm
}

func TestOnlyOurImagesCanBeStarted(t *testing.T) {
	m := sandboxd.NewManager(newFake(), limits)
	for _, image := range []string{"ubuntu", "node:20", "", "talnex-sandbox-x; rm -rf /", "evil/talnex-sandbox-node"} {
		_, err := m.Create(context.Background(), sandboxd.CreateRequest{Image: image})
		if !errors.Is(err, sandboxd.ErrBadRequest) {
			t.Errorf("image %q: got %v, want a bad request", image, err)
		}
	}
}

func TestAskingForMoreThanTheHostAllowsIsCapped(t *testing.T) {
	d := newFake()
	m := sandboxd.NewManager(d, limits)
	vm, err := m.Create(context.Background(), sandboxd.CreateRequest{Image: "talnex-sandbox-node", CPUs: 64, MemoryMB: 999999, TimeLimitSeconds: 99999})
	if err != nil {
		t.Fatal(err)
	}
	got := d.created[vm.ID]
	if got.CPUs != 2 || got.MemoryMB != 1024 || got.TimeLimit != 10*time.Minute {
		t.Errorf("spec = %+v", got)
	}
	small, _ := m.Create(context.Background(), sandboxd.CreateRequest{Image: "talnex-sandbox-node", CPUs: 1, MemoryMB: 256, TimeLimitSeconds: 60})
	if s := d.created[small.ID]; s.CPUs != 1 || s.MemoryMB != 256 || s.TimeLimit != time.Minute {
		t.Errorf("a smaller ask should be kept: %+v", s)
	}
}

func TestTheHostNeverRunsMoreVMsThanItMayAndAFailedCreateFreesTheSlot(t *testing.T) {
	d := newFake()
	m := sandboxd.NewManager(d, limits)
	a, b := newVM(t, m), newVM(t, m)
	if _, err := m.Create(context.Background(), sandboxd.CreateRequest{Image: "talnex-sandbox-node"}); !errors.Is(err, sandboxd.ErrBusy) {
		t.Fatalf("third VM: %v, want busy", err)
	}
	if err := m.Destroy(context.Background(), a.ID); err != nil {
		t.Fatal(err)
	}
	d.failNext = errors.New("docker is unhappy")
	if _, err := m.Create(context.Background(), sandboxd.CreateRequest{Image: "talnex-sandbox-node"}); err == nil {
		t.Fatal("expected the driver error")
	}
	if running, _ := m.Counts(); running != 1 { // only b is left: the failed create gave its place back
		t.Errorf("running = %d, want 1", running)
	}
	_ = b
}

func TestAVMPastItsTimeLimitIsGoneAndTheReaperDestroysIt(t *testing.T) {
	d := newFake()
	m := sandboxd.NewManager(d, limits)
	now := time.Now()
	m.SetClock(func() time.Time { return now })
	vm := newVM(t, m)
	if _, err := m.Get(vm.ID); err != nil {
		t.Fatal(err)
	}
	now = now.Add(11 * time.Minute)
	if _, err := m.Get(vm.ID); !errors.Is(err, sandboxd.ErrNotFound) {
		t.Errorf("expired VM: %v", err)
	}
	if _, err := m.Exec(context.Background(), vm.ID, sandboxd.ExecSpec{Command: []string{"ls"}}); !errors.Is(err, sandboxd.ErrNotFound) {
		t.Errorf("exec on an expired VM: %v", err)
	}
	if n := m.Reap(context.Background()); n != 1 || len(d.destroyed) != 1 {
		t.Errorf("reaped %d, destroyed %v", n, d.destroyed)
	}
}

func TestStartUpCleanupDestroysEveryVMTheDriverStillHas(t *testing.T) {
	d := newFake()
	d.created["left-over-1"], d.created["left-over-2"] = sandboxd.VMSpec{}, sandboxd.VMSpec{}
	m := sandboxd.NewManager(d, limits)
	if n, err := m.DestroyAll(context.Background()); err != nil || n != 2 || len(d.created) != 0 {
		t.Errorf("destroyed %d, err %v, left %v", n, err, d.created)
	}
}

func TestExecIsCappedByTheHostTimeoutAndNeedsACommand(t *testing.T) {
	d := newFake()
	m := sandboxd.NewManager(d, limits)
	vm := newVM(t, m)
	if _, err := m.Exec(context.Background(), vm.ID, sandboxd.ExecSpec{}); !errors.Is(err, sandboxd.ErrBadRequest) {
		t.Errorf("empty command: %v", err)
	}
	_, _ = m.Exec(context.Background(), vm.ID, sandboxd.ExecSpec{Command: []string{"make"}, Timeout: time.Hour})
	_, _ = m.Exec(context.Background(), vm.ID, sandboxd.ExecSpec{Command: []string{"make"}})
	if d.execs[0].Timeout != 5*time.Minute || d.execs[1].Timeout != 5*time.Minute {
		t.Errorf("timeouts = %v, %v", d.execs[0].Timeout, d.execs[1].Timeout)
	}
}

func TestUploadNeedsASafeDirectory(t *testing.T) {
	m := sandboxd.NewManager(newFake(), limits)
	vm := newVM(t, m)
	for _, dir := range []string{"work", "../etc", "/work/../etc"} {
		if err := m.Upload(context.Background(), vm.ID, dir, strings.NewReader("x")); !errors.Is(err, sandboxd.ErrBadRequest) {
			t.Errorf("dir %q: %v", dir, err)
		}
	}
	if err := m.Upload(context.Background(), vm.ID, "/work", strings.NewReader("x")); err != nil {
		t.Errorf("good dir: %v", err)
	}
}

// ---- ports and HTTP requests ----

const procNetTCP = `  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12345 1 0 100 0 0 10 0
   1: 0100007F:0BB8 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12346 1 0 100 0 0 10 0
   2: 0100007F:C350 0100007F:1F90 01 00000000:00000000 00:00000000 00000000     0        0 12347 1 0 100 0 0 10 0
   3: 00000000:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12348 1 0 100 0 0 10 0`

func TestListeningPortsAreReadFromProcNetTCP(t *testing.T) {
	got := sandboxd.ParseListeningPorts(procNetTCP)
	if len(got) != 2 || got[0] != 3000 || got[1] != 8080 { // 0BB8 = 3000, 1F90 = 8080; the connected socket (state 01) is ignored
		t.Errorf("ports = %v", got)
	}
	if got := sandboxd.ParseListeningPorts("garbage\n"); len(got) != 0 {
		t.Errorf("garbage gave %v", got)
	}
}

func answer(stdout string, code int, stderr string) func(sandboxd.ExecSpec) sandboxd.ExecResult {
	return func(sandboxd.ExecSpec) sandboxd.ExecResult {
		return sandboxd.ExecResult{ExitCode: code, Stdout: stdout, Stderr: stderr}
	}
}

func TestARequestIsSentFromInsideTheVMAndTheAnswerIsParsed(t *testing.T) {
	d := newFake()
	m := sandboxd.NewManager(d, limits)
	vm := newVM(t, m)
	d.reply = answer("HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 201 Created\r\nContent-Type: application/json\r\nX-Id: 7\r\n\r\n{\"ok\":true}", 0, "")

	res, err := m.Request(context.Background(), vm.ID, sandboxd.HTTPRequest{
		Method: "post", Port: 3000, Path: "/items?x=1", Headers: map[string]string{"Authorization": "Bearer t", "Content-Type": "application/json"}, Body: []byte(`{"a":1}`),
	})
	if err != nil {
		t.Fatal(err)
	}
	if res.Status != 201 || string(res.Body) != `{"ok":true}` || res.Headers["Content-Type"][0] != "application/json" || res.Headers["X-Id"][0] != "7" || res.Error != "" {
		t.Errorf("response = %+v", res)
	}
	sent := d.execs[len(d.execs)-1]
	line := strings.Join(sent.Command, " ")
	for _, want := range []string{"curl", "-X POST", "-H Authorization: Bearer t", "--data-binary @-", "http://127.0.0.1:3000/items?x=1"} {
		if !strings.Contains(line, want) {
			t.Errorf("command %q lacks %q", line, want)
		}
	}
	if string(sent.Stdin) != `{"a":1}` {
		t.Errorf("stdin = %q", sent.Stdin)
	}
}

func TestAnAppThatDoesNotAnswerIsAResultNotAHostError(t *testing.T) {
	d := newFake()
	m := sandboxd.NewManager(d, limits)
	vm := newVM(t, m)
	for code, want := range map[int]string{7: "connection refused", 28: "did not answer in time", 52: "closed the connection"} {
		d.reply = answer("", code, "")
		res, err := m.Request(context.Background(), vm.ID, sandboxd.HTTPRequest{Port: 3000, Path: "/"})
		if err != nil || res.Status != 0 || !strings.Contains(res.Error, want) {
			t.Errorf("curl exit %d: res %+v err %v, want error containing %q", code, res, err, want)
		}
	}
	d.reply = answer("not http at all", 0, "")
	if res, _ := m.Request(context.Background(), vm.ID, sandboxd.HTTPRequest{Port: 3000, Path: "/"}); res.Error == "" {
		t.Error("a non-HTTP answer should be reported")
	}
}

func TestRequestRefusesWhatCouldSmuggleExtraCommandsOrHeaders(t *testing.T) {
	m := sandboxd.NewManager(newFake(), limits)
	vm := newVM(t, m)
	cases := map[string]sandboxd.HTTPRequest{
		"bad method":          {Method: "TRACE", Port: 80, Path: "/"},
		"port zero":           {Port: 0, Path: "/"},
		"port too big":        {Port: 70000, Path: "/"},
		"path without slash":  {Port: 80, Path: "items"},
		"path with a space":   {Port: 80, Path: "/a b"},
		"path with a newline": {Port: 80, Path: "/a\nb"},
		"header with newline": {Port: 80, Path: "/", Headers: map[string]string{"X": "a\r\nInjected: 1"}},
		"header name colon":   {Port: 80, Path: "/", Headers: map[string]string{"A:B": "x"}},
	}
	for name, req := range cases {
		if _, err := m.Request(context.Background(), vm.ID, req); !errors.Is(err, sandboxd.ErrBadRequest) {
			t.Errorf("%s: got %v, want a bad request", name, err)
		}
	}
}

func TestServicesAreCleanedValidatedAndPassedToTheDriver(t *testing.T) {
	d := newFake()
	m := sandboxd.NewManager(d, limits)

	vm, err := m.Create(context.Background(), sandboxd.CreateRequest{Image: "talnex-sandbox-full", Services: []string{"Postgres", "redis", "postgres"}})
	if err != nil {
		t.Fatal(err)
	}
	if got := d.created[vm.ID].Services; len(got) != 2 || got[0] != "postgres" || got[1] != "redis" {
		t.Errorf("services = %v (should be deduped and lowercased)", got)
	}

	if _, err := m.Create(context.Background(), sandboxd.CreateRequest{Image: "talnex-sandbox-full", Services: []string{"mysql"}}); err == nil {
		t.Error("an unknown service should be refused")
	}
	if _, err := m.Create(context.Background(), sandboxd.CreateRequest{Image: "talnex-sandbox-full", Services: []string{"postgres", "redis", "mongo"}}); err == nil {
		t.Errorf("more than %d services should be refused", sandboxd.MaxServices)
	}
}
