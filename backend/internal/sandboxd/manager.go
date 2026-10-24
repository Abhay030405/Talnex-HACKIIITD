package sandboxd

import (
	"context"
	"fmt"
	"io"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
)

// maxUpload is the biggest archive that may be copied into a VM.
const maxUpload = 200 << 20

// VM is what the host knows about one running VM.
type VM struct {
	ID        string    `json:"id"`
	Image     string    `json:"image"`
	CreatedAt time.Time `json:"created_at"`
	ExpiresAt time.Time `json:"expires_at"`
}

// CreateRequest asks for a VM. Zero values mean "the host's default"; asking for more than the host allows is capped.
type CreateRequest struct {
	Image            string `json:"image"`
	CPUs             int    `json:"cpus"`
	MemoryMB         int    `json:"memory_mb"`
	TimeLimitSeconds int    `json:"time_limit_seconds"`
}

// Manager applies the host's rules on top of a driver.
type Manager struct {
	drv Driver
	lim Limits
	now func() time.Time

	mu  sync.Mutex
	vms map[string]*VM
}

func NewManager(drv Driver, lim Limits) *Manager {
	return &Manager{drv: drv, lim: lim, now: time.Now, vms: map[string]*VM{}}
}

// SetClock replaces the clock. For tests.
func (m *Manager) SetClock(now func() time.Time) { m.now = now }

func bad(format string, args ...any) error {
	return fmt.Errorf("%w: %s", ErrBadRequest, fmt.Sprintf(format, args...))
}

func (m *Manager) Ping(ctx context.Context) error { return m.drv.Ping(ctx) }

// Counts returns how many VMs run now and how many may.
func (m *Manager) Counts() (running, max int) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.vms), m.lim.MaxVMs
}

// Create makes a fresh VM. A VM is never reused between projects: the caller makes one per run and destroys it.
func (m *Manager) Create(ctx context.Context, req CreateRequest) (VM, error) {
	if !strings.HasPrefix(req.Image, ImagePrefix) {
		return VM{}, bad("image must be one of ours (it starts with %q)", ImagePrefix)
	}
	if strings.ContainsAny(req.Image, " \t\r\n;&|$`'\"\\") {
		return VM{}, bad("image name has characters that are not allowed")
	}
	spec := VMSpec{
		Image:     req.Image,
		CPUs:      capInt(req.CPUs, m.lim.CPUs),
		MemoryMB:  capInt(req.MemoryMB, m.lim.MemoryMB),
		TimeLimit: time.Duration(capInt(req.TimeLimitSeconds, int(m.lim.TimeLimit.Seconds()))) * time.Second,
	}

	id := uuid.NewString()
	now := m.now()
	vm := &VM{ID: id, Image: spec.Image, CreatedAt: now, ExpiresAt: now.Add(spec.TimeLimit)}

	// Take the place first, so two calls at the same moment cannot both pass the limit.
	m.mu.Lock()
	if len(m.vms) >= m.lim.MaxVMs {
		m.mu.Unlock()
		return VM{}, ErrBusy
	}
	m.vms[id] = vm
	m.mu.Unlock()

	if err := m.drv.Create(ctx, id, spec); err != nil {
		m.forget(id)
		return VM{}, fmt.Errorf("create VM: %w", err)
	}
	return *vm, nil
}

// capInt returns the asked value when it is positive and not above the allowed one, else the allowed one.
func capInt(asked, allowed int) int {
	if asked <= 0 || asked > allowed {
		return allowed
	}
	return asked
}

func (m *Manager) forget(id string) {
	m.mu.Lock()
	delete(m.vms, id)
	m.mu.Unlock()
}

// Get returns a VM that exists and has not expired.
func (m *Manager) Get(id string) (VM, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	vm, ok := m.vms[id]
	if !ok || !m.now().Before(vm.ExpiresAt) {
		return VM{}, ErrNotFound
	}
	return *vm, nil
}

// List returns the VMs that are running, oldest first.
func (m *Manager) List() []VM {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]VM, 0, len(m.vms))
	for _, vm := range m.vms {
		out = append(out, *vm)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].CreatedAt.Before(out[j].CreatedAt) })
	return out
}

// Upload unpacks a tar archive into a directory of the VM. The archive must be a tar stream.
func (m *Manager) Upload(ctx context.Context, id, dir string, archive io.Reader) error {
	if _, err := m.Get(id); err != nil {
		return err
	}
	if !strings.HasPrefix(dir, "/") || strings.Contains(dir, "..") {
		return bad("dir must be an absolute path inside the VM, without ..")
	}
	if _, err := m.run(ctx, id, ExecSpec{Command: []string{"mkdir", "-p", dir}, Timeout: 30 * time.Second}); err != nil {
		return err
	}
	return m.drv.CopyIn(ctx, id, dir, io.LimitReader(archive, maxUpload))
}

// Exec runs a command in a VM. Its time is capped by the host's limit; a command that runs out of time is
// reported as timed out, never as an error of the host.
func (m *Manager) Exec(ctx context.Context, id string, spec ExecSpec) (ExecResult, error) {
	if _, err := m.Get(id); err != nil {
		return ExecResult{}, err
	}
	if len(spec.Command) == 0 {
		return ExecResult{}, bad("command is empty")
	}
	return m.run(ctx, id, spec)
}

func (m *Manager) run(ctx context.Context, id string, spec ExecSpec) (ExecResult, error) {
	if spec.Timeout <= 0 || spec.Timeout > m.lim.ExecTimeout {
		spec.Timeout = m.lim.ExecTimeout
	}
	return m.drv.Exec(ctx, id, spec)
}

// Destroy removes a VM. Destroying one that is already gone is not an error.
func (m *Manager) Destroy(ctx context.Context, id string) error {
	m.forget(id)
	return m.drv.Destroy(ctx, id)
}

// Reap destroys every VM past its time limit and returns how many it removed. The daemon calls it on a timer.
func (m *Manager) Reap(ctx context.Context) int {
	m.mu.Lock()
	var expired []string
	for id, vm := range m.vms {
		if !m.now().Before(vm.ExpiresAt) {
			expired = append(expired, id)
		}
	}
	m.mu.Unlock()
	n := 0
	for _, id := range expired {
		if err := m.Destroy(ctx, id); err == nil {
			n++
		}
	}
	return n
}

// DestroyAll removes every VM the driver is running, including ones left by an earlier run of the daemon.
// VMs are per-run and never reused, so at start-up nothing that exists is worth keeping.
func (m *Manager) DestroyAll(ctx context.Context) (int, error) {
	ids, err := m.drv.List(ctx)
	if err != nil {
		return 0, err
	}
	n := 0
	for _, id := range ids {
		if err := m.Destroy(ctx, id); err == nil {
			n++
		}
	}
	return n, nil
}
