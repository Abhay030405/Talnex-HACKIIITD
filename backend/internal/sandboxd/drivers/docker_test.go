package drivers

import (
	"bytes"
	"context"
	"errors"
	"io"
	"strings"
	"testing"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd"
)

// script is a stand-in for the docker program. It records each call and answers from a function.
type script struct {
	calls  [][]string
	stdins []string
	reply  func(args []string) (stdout, stderr string, code int)
}

func (s *script) cli() cli {
	return func(ctx context.Context, stdin io.Reader, stdout, stderr io.Writer, args ...string) (int, error) {
		s.calls = append(s.calls, args)
		in := ""
		if stdin != nil {
			b, _ := io.ReadAll(stdin)
			in = string(b)
		}
		s.stdins = append(s.stdins, in)
		out, errText, code := "", "", 0
		if s.reply != nil {
			out, errText, code = s.reply(args)
		}
		_, _ = stdout.Write([]byte(out))
		_, _ = stderr.Write([]byte(errText))
		return code, nil
	}
}

func driver(s *script) *Docker { return &Docker{run: s.cli()} }

func TestCreateSetsEveryLimitAndLabelsTheContainer(t *testing.T) {
	s := &script{}
	err := driver(s).Create(context.Background(), "abc", sandboxd.VMSpec{Image: "talnex-sandbox-node", CPUs: 2, MemoryMB: 1024, TimeLimit: 10 * time.Minute})
	if err != nil {
		t.Fatal(err)
	}
	line := strings.Join(s.calls[0], " ")
	for _, want := range []string{"run -d --init", "--name talnex-vm-abc", "--label talnex.sandbox=1", "--label talnex.vm=abc", "--cpus 2",
		"--memory 1024m", "--memory-swap 1024m", "--pids-limit 1024", "no-new-privileges", "talnex-sandbox-node sleep 660"} {
		if !strings.Contains(line, want) {
			t.Errorf("docker %s\n lacks %q", line, want)
		}
	}
}

func TestACommandIsRunInsideTheVMWithATimeLimitOfItsOwn(t *testing.T) {
	s := &script{reply: func([]string) (string, string, int) { return "hi\n", "", 0 }}
	res, err := driver(s).Exec(context.Background(), "abc", sandboxd.ExecSpec{
		Command: []string{"sh", "-c", "echo hi"}, Env: map[string]string{"B": "2", "A": "1"}, WorkDir: "/work/app", Timeout: 90 * time.Second, Stdin: []byte("in"),
	})
	if err != nil || res.Stdout != "hi\n" || res.ExitCode != 0 || res.TimedOut {
		t.Fatalf("res %+v err %v", res, err)
	}
	line := strings.Join(s.calls[0], " ")
	want := "exec -i -w /work/app -e A=1 -e B=2 talnex-vm-abc timeout -k 5 90 sh -c echo hi"
	if line != want {
		t.Errorf("docker %s\n want %s", line, want)
	}
	if s.stdins[0] != "in" {
		t.Errorf("stdin = %q", s.stdins[0])
	}
}

func TestADetachedCommandIsNotWrappedInTimeout(t *testing.T) {
	s := &script{}
	_, err := driver(s).Exec(context.Background(), "abc", sandboxd.ExecSpec{Command: []string{"sh", "-c", "npm start > /tmp/app.log 2>&1"}, Detach: true})
	if err != nil {
		t.Fatal(err)
	}
	if line := strings.Join(s.calls[0], " "); line != "exec -d talnex-vm-abc sh -c npm start > /tmp/app.log 2>&1" {
		t.Errorf("docker %s", line)
	}
}

func TestACommandThatRunsOutOfTimeIsReportedAsTimedOutNotAsAHostError(t *testing.T) {
	s := &script{reply: func([]string) (string, string, int) { return "partial", "", 124 }}
	res, err := driver(s).Exec(context.Background(), "abc", sandboxd.ExecSpec{Command: []string{"sleep", "99"}, Timeout: time.Second})
	if err != nil || !res.TimedOut || res.ExitCode != 124 {
		t.Errorf("res %+v err %v", res, err)
	}
}

func TestAFailingCommandIsAResultAndADockerFailureIsAnError(t *testing.T) {
	s := &script{reply: func([]string) (string, string, int) { return "", "npm ERR! missing script", 1 }}
	res, err := driver(s).Exec(context.Background(), "abc", sandboxd.ExecSpec{Command: []string{"npm", "test"}, Timeout: time.Second})
	if err != nil || res.ExitCode != 1 || !strings.Contains(res.Stderr, "npm ERR!") {
		t.Errorf("a failing command: res %+v err %v", res, err)
	}
	s.reply = func([]string) (string, string, int) {
		return "", "Error response from daemon: No such container: talnex-vm-abc", 1
	}
	if _, err := driver(s).Exec(context.Background(), "abc", sandboxd.ExecSpec{Command: []string{"ls"}, Timeout: time.Second}); !errors.Is(err, sandboxd.ErrNotFound) {
		t.Errorf("a missing container: %v", err)
	}
	s.reply = func([]string) (string, string, int) { return "", "docker: container is not running", 126 }
	if _, err := driver(s).Exec(context.Background(), "abc", sandboxd.ExecSpec{Command: []string{"ls"}, Timeout: time.Second}); err == nil {
		t.Error("docker refusing to run the command should be an error")
	}
}

func TestEnvironmentNamesAreChecked(t *testing.T) {
	_, err := driver(&script{}).Exec(context.Background(), "abc", sandboxd.ExecSpec{Command: []string{"ls"}, Env: map[string]string{"A=B C": "x"}})
	if !errors.Is(err, sandboxd.ErrBadRequest) {
		t.Errorf("got %v", err)
	}
}

func TestOnlyTheEndOfALongOutputIsKept(t *testing.T) {
	big := strings.Repeat("a", maxOutput) + "THE END"
	s := &script{reply: func([]string) (string, string, int) { return big, "", 1 }}
	res, _ := driver(s).Exec(context.Background(), "abc", sandboxd.ExecSpec{Command: []string{"make"}, Timeout: time.Second})
	if !res.Truncated || len(res.Stdout) != maxOutput || !strings.HasSuffix(res.Stdout, "THE END") {
		t.Errorf("truncated=%v len=%d", res.Truncated, len(res.Stdout))
	}
}

func TestCopyInSendsTheArchiveOnStandardInput(t *testing.T) {
	s := &script{}
	if err := driver(s).CopyIn(context.Background(), "abc", "/work", bytes.NewReader([]byte("TARDATA"))); err != nil {
		t.Fatal(err)
	}
	if line := strings.Join(s.calls[0], " "); line != "cp - talnex-vm-abc:/work" || s.stdins[0] != "TARDATA" {
		t.Errorf("docker %s stdin %q", line, s.stdins[0])
	}
}

func TestDestroyIsFineWhenTheContainerIsAlreadyGone(t *testing.T) {
	s := &script{reply: func([]string) (string, string, int) {
		return "", "Error response from daemon: No such container: talnex-vm-abc", 1
	}}
	if err := driver(s).Destroy(context.Background(), "abc"); err != nil {
		t.Errorf("got %v", err)
	}
	s.reply = func([]string) (string, string, int) { return "", "permission denied", 1 }
	if err := driver(s).Destroy(context.Background(), "abc"); err == nil {
		t.Error("a real failure should be reported")
	}
}

func TestListReturnsTheIdsOfOurContainersOnly(t *testing.T) {
	s := &script{reply: func([]string) (string, string, int) { return "id-1\nid-2\n\n", "", 0 }}
	ids, err := driver(s).List(context.Background())
	if err != nil || len(ids) != 2 || ids[0] != "id-1" {
		t.Errorf("ids %v err %v", ids, err)
	}
	if line := strings.Join(s.calls[0], " "); !strings.Contains(line, "label=talnex.role=app") {
		t.Errorf("list should count only the VM containers, not the backing stores: docker %s", line)
	}
}

func TestServicesRunOnAPrivateNetworkTheVMJoins(t *testing.T) {
	s := &script{}
	err := driver(s).Create(context.Background(), "abc", sandboxd.VMSpec{
		Image: "talnex-sandbox-full", CPUs: 2, MemoryMB: 1024, TimeLimit: 10 * time.Minute, Services: []string{"postgres"}})
	if err != nil {
		t.Fatal(err)
	}
	var netCreate, svcRun, appRun string
	for _, c := range s.calls {
		line := strings.Join(c, " ")
		switch {
		case strings.HasPrefix(line, "network create"):
			netCreate = line
		case strings.Contains(line, "talnex-svc-abc-postgres"):
			svcRun = line
		case strings.Contains(line, "--name talnex-vm-abc"):
			appRun = line
		}
	}
	if !strings.Contains(netCreate, "talnex-net-abc") {
		t.Errorf("no private network was created: %q", netCreate)
	}
	for _, want := range []string{"--network talnex-net-abc", "--network-alias postgres", "-e POSTGRES_PASSWORD=talnex",
		"-e POSTGRES_USER=talnex", "postgres:16-alpine", "talnex.role=svc"} {
		if !strings.Contains(svcRun, want) {
			t.Errorf("service run\n %s\n lacks %q", svcRun, want)
		}
	}
	for _, want := range []string{"--network talnex-net-abc", "--network-alias app", "talnex.role=app"} {
		if !strings.Contains(appRun, want) {
			t.Errorf("app run\n %s\n lacks %q", appRun, want)
		}
	}
}

func TestDestroyRemovesEveryContainerOfTheVMAndItsNetwork(t *testing.T) {
	s := &script{reply: func(args []string) (string, string, int) {
		if len(args) >= 2 && args[0] == "ps" {
			return "cid_app\ncid_pg\n", "", 0
		}
		return "", "", 0
	}}
	if err := driver(s).Destroy(context.Background(), "abc"); err != nil {
		t.Fatal(err)
	}
	var rm, netRm bool
	for _, c := range s.calls {
		line := strings.Join(c, " ")
		if strings.HasPrefix(line, "rm -f") && strings.Contains(line, "cid_app") && strings.Contains(line, "cid_pg") {
			rm = true
		}
		if line == "network rm talnex-net-abc" {
			netRm = true
		}
	}
	if !rm {
		t.Error("destroy should remove every container of the VM in one rm")
	}
	if !netRm {
		t.Error("destroy should remove the private network")
	}
}
