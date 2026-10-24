// Package drivers holds the machine-level back ends of sandboxd. The docker driver runs each VM as a container on
// a Linux Docker engine (Docker Desktop on a laptop works). A firecracker driver can sit beside it later.
package drivers

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os/exec"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd"
)

const (
	labelAll = "talnex.sandbox"
	labelVM  = "talnex.vm"
	// A container stays alive a little past the VM's time limit by itself, so a crashed daemon cannot leave one
	// running forever even before the reaper looks.
	selfDestructSlack = 60 * time.Second
	// maxOutput is how much of a command's output is kept (the last part, since the end of a failed build matters most).
	maxOutput = 256 << 10
	// cliSlack is extra time given to the docker program itself beyond the command's own time limit.
	cliSlack = 15 * time.Second
)

var envName = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

// cli runs the docker program. It is a field so tests can replace it.
type cli func(ctx context.Context, stdin io.Reader, stdout, stderr io.Writer, args ...string) (exitCode int, err error)

// Docker is the docker driver.
type Docker struct {
	run cli
}

// NewDocker uses the `docker` program found on the PATH of the sandbox host.
func NewDocker() *Docker { return &Docker{run: realCLI("docker")} }

func realCLI(bin string) cli {
	return func(ctx context.Context, stdin io.Reader, stdout, stderr io.Writer, args ...string) (int, error) {
		cmd := exec.CommandContext(ctx, bin, args...)
		cmd.Stdin, cmd.Stdout, cmd.Stderr = stdin, stdout, stderr
		hideWindow(cmd)
		err := cmd.Run()
		var ee *exec.ExitError
		if errors.As(err, &ee) {
			return ee.ExitCode(), nil
		}
		if err != nil {
			return -1, err
		}
		return 0, nil
	}
}

func name(id string) string { return "talnex-vm-" + id }

// simple runs a docker command and returns its stdout, or an error carrying docker's own message.
func (d *Docker) simple(ctx context.Context, stdin io.Reader, args ...string) (string, error) {
	var out, errb bytes.Buffer
	code, err := d.run(ctx, stdin, &out, &errb, args...)
	if err != nil {
		return "", fmt.Errorf("docker %s: %w", args[0], err)
	}
	if code != 0 {
		return "", fmt.Errorf("docker %s: %s", args[0], strings.TrimSpace(errb.String()))
	}
	return out.String(), nil
}

func (d *Docker) Ping(ctx context.Context) error {
	_, err := d.simple(ctx, nil, "version", "--format", "{{.Server.Version}}")
	return err
}

func (d *Docker) Create(ctx context.Context, id string, spec sandboxd.VMSpec) error {
	life := int((spec.TimeLimit + selfDestructSlack).Seconds())
	_, err := d.simple(ctx, nil, "run", "-d", "--init",
		"--name", name(id),
		"--label", labelAll+"=1", "--label", labelVM+"="+id,
		"--cpus", strconv.Itoa(spec.CPUs),
		"--memory", strconv.Itoa(spec.MemoryMB)+"m", "--memory-swap", strconv.Itoa(spec.MemoryMB)+"m",
		"--pids-limit", "1024",
		"--security-opt", "no-new-privileges",
		"-w", "/work",
		spec.Image, "sleep", strconv.Itoa(life))
	return err
}

func (d *Docker) CopyIn(ctx context.Context, id, dir string, archive io.Reader) error {
	_, err := d.simple(ctx, archive, "cp", "-", name(id)+":"+dir)
	return err
}

func (d *Docker) Exec(ctx context.Context, id string, spec sandboxd.ExecSpec) (sandboxd.ExecResult, error) {
	if len(spec.Command) == 0 {
		return sandboxd.ExecResult{}, errors.New("empty command")
	}
	args := []string{"exec"}
	if spec.Detach {
		args = append(args, "-d")
	}
	if len(spec.Stdin) > 0 {
		args = append(args, "-i")
	}
	if spec.WorkDir != "" {
		args = append(args, "-w", spec.WorkDir)
	}
	keys := make([]string, 0, len(spec.Env))
	for k := range spec.Env {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		if !envName.MatchString(k) {
			return sandboxd.ExecResult{}, fmt.Errorf("%w: %q is not a valid environment name", sandboxd.ErrBadRequest, k)
		}
		args = append(args, "-e", k+"="+spec.Env[k])
	}
	args = append(args, name(id))
	command := spec.Command
	if !spec.Detach {
		// The time limit is enforced inside the VM too. Killing the docker program alone would leave the command running.
		secs := int(spec.Timeout.Seconds())
		if secs < 1 {
			secs = 1
		}
		command = append([]string{"timeout", "-k", "5", strconv.Itoa(secs)}, command...)
	}
	args = append(args, command...)

	runCtx := ctx
	if spec.Timeout > 0 {
		var cancel context.CancelFunc
		runCtx, cancel = context.WithTimeout(ctx, spec.Timeout+cliSlack)
		defer cancel()
	}
	var stdin io.Reader
	if len(spec.Stdin) > 0 {
		stdin = bytes.NewReader(spec.Stdin)
	}
	out, errb := &tail{limit: maxOutput}, &tail{limit: maxOutput}
	started := time.Now()
	code, err := d.run(runCtx, stdin, out, errb, args...)
	res := sandboxd.ExecResult{
		ExitCode: code, Stdout: out.String(), Stderr: errb.String(),
		DurationMS: time.Since(started).Milliseconds(), Truncated: out.cut || errb.cut,
	}
	if err != nil {
		if errors.Is(runCtx.Err(), context.DeadlineExceeded) {
			res.TimedOut = true
			return res, nil
		}
		return res, fmt.Errorf("docker exec: %w", err)
	}
	// `timeout` answers 124 when it stopped the command; docker itself answers 125 to 127 when it could not run it.
	if code == 124 {
		res.TimedOut = true
	}
	if code == 125 || (code == 126 && strings.Contains(res.Stderr, "container")) {
		return res, fmt.Errorf("docker exec: %s", strings.TrimSpace(res.Stderr))
	}
	if strings.Contains(res.Stderr, "No such container") {
		return res, sandboxd.ErrNotFound
	}
	return res, nil
}

func (d *Docker) Destroy(ctx context.Context, id string) error {
	_, err := d.simple(ctx, nil, "rm", "-f", name(id))
	if err != nil && strings.Contains(err.Error(), "No such container") {
		return nil // already gone
	}
	return err
}

func (d *Docker) List(ctx context.Context) ([]string, error) {
	out, err := d.simple(ctx, nil, "ps", "-aq", "--filter", "label="+labelAll+"=1", "--format", `{{.Label "`+labelVM+`"}}`)
	if err != nil {
		return nil, err
	}
	var ids []string
	for _, line := range strings.Split(out, "\n") {
		if id := strings.TrimSpace(line); id != "" {
			ids = append(ids, id)
		}
	}
	return ids, nil
}

// tail keeps the last `limit` bytes written to it and remembers that it dropped the start.
type tail struct {
	limit int
	buf   []byte
	cut   bool
}

func (t *tail) Write(p []byte) (int, error) {
	t.buf = append(t.buf, p...)
	if len(t.buf) > t.limit {
		t.buf = append([]byte(nil), t.buf[len(t.buf)-t.limit:]...)
		t.cut = true
	}
	return len(p), nil
}

func (t *tail) String() string { return string(t.buf) }
