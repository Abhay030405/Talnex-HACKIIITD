// Package sandboxd is the engine of the VM host daemon (architecture section 28).
//
// It knows nothing about TalNex: no database, no jobs, no keys. It creates a throwaway VM from one of our prebuilt
// images, copies files in, runs commands, sends HTTP requests to the app inside, and destroys the VM. A Driver does
// the machine-level work (docker now, firecracker later); the Manager adds the rules that hold for every driver:
// a limit on how many VMs run at once, caps on size and time, and the expiry the reaper enforces.
package sandboxd

import (
	"context"
	"errors"
	"io"
	"time"
)

var (
	// ErrNotFound means there is no such VM (it never existed, or it was destroyed or expired).
	ErrNotFound = errors.New("no such VM")
	// ErrBusy means the host is running as many VMs as it may; the caller should wait and try again.
	ErrBusy = errors.New("the host is running its maximum number of VMs")
	// ErrBadRequest wraps every problem with what the caller asked for.
	ErrBadRequest = errors.New("bad request")
)

// ImagePrefix is the only kind of image a VM may be made from: ours. Nothing else can be started.
const ImagePrefix = "talnex-sandbox-"

// VMSpec is what a driver needs to make a VM.
type VMSpec struct {
	Image     string
	CPUs      int
	MemoryMB  int
	TimeLimit time.Duration
	// Services are backing stores the repo needs (for example "postgres", "redis"). Each runs as its own throwaway
	// container on a private network beside the VM, reachable from it by the service name. Only names in ServiceCatalog
	// are allowed; anything else is refused. Empty = the VM runs on its own, as before.
	Services []string
}

// ServiceSpec is one backing store the sandbox can start beside a VM. Fixed, local-only credentials: a sandbox holds no
// real data and is destroyed after the run.
type ServiceSpec struct {
	Image string            // the official image to run
	Port  int               // the port it listens on, inside the private network
	Env   map[string]string // environment the container needs to start
	URL   string            // how the repo reaches it; {host} is the service name on the network
}

// ServiceCatalog is every backing store the sandbox knows how to start. Nothing outside it can be started.
var ServiceCatalog = map[string]ServiceSpec{
	"postgres": {Image: "postgres:16-alpine", Port: 5432,
		Env: map[string]string{"POSTGRES_USER": "talnex", "POSTGRES_PASSWORD": "talnex", "POSTGRES_DB": "talnex"},
		URL: "postgres://talnex:talnex@{host}:5432/talnex"},
	"redis":   {Image: "redis:7-alpine", Port: 6379, URL: "redis://{host}:6379"},
	"mongodb": {Image: "mongo:7", Port: 27017, URL: "mongodb://{host}:27017"},
}

// MaxServices is the most backing stores one VM may ask for.
const MaxServices = 2

// ExecSpec is one command to run inside a VM.
type ExecSpec struct {
	Command []string          // the program and its arguments
	Stdin   []byte            // optional input
	Env     map[string]string // extra environment for this command only
	WorkDir string
	Timeout time.Duration
	Detach  bool // start it and return at once (for a server); the caller sends its output to a file
}

// ExecResult is what a command did. Output is the tail of what it printed, so the last lines of a failed build are kept.
type ExecResult struct {
	ExitCode   int    `json:"exit_code"`
	Stdout     string `json:"stdout"`
	Stderr     string `json:"stderr"`
	DurationMS int64  `json:"duration_ms"`
	TimedOut   bool   `json:"timed_out"`
	Truncated  bool   `json:"truncated"`
}

// Driver does the machine-level work. One interface so docker can be swapped for firecracker without touching callers.
type Driver interface {
	Ping(ctx context.Context) error
	Create(ctx context.Context, id string, spec VMSpec) error
	CopyIn(ctx context.Context, id, dir string, archive io.Reader) error
	Exec(ctx context.Context, id string, spec ExecSpec) (ExecResult, error)
	Destroy(ctx context.Context, id string) error
	// List returns the ids of the VMs the driver is running, whether or not this process made them.
	List(ctx context.Context) ([]string, error)
}

// Limits are the rules every call is held to.
type Limits struct {
	MaxVMs      int
	CPUs        int
	MemoryMB    int
	TimeLimit   time.Duration
	ExecTimeout time.Duration
}
