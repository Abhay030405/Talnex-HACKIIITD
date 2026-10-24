package config

import "time"

// Sandboxd holds the settings of the VM host daemon (architecture section 28). sandboxd is its own program on the
// sandbox host; it never reads the database or any TalNex key, so it has its own small loader.
type Sandboxd struct {
	ListenAddr  string        // where sandboxd listens, for example 0.0.0.0:7070
	Token       string        // every call except /healthz must carry it
	Driver      string        // docker (firecracker later)
	MaxVMs      int           // how many VMs may run at once; more calls are told to wait
	CPUs        int           // CPUs given to a VM unless the call asks for fewer
	MemoryMB    int           // memory given to a VM unless the call asks for less
	TimeLimit   time.Duration // the longest a VM may live; the reaper destroys it after this
	ExecTimeout time.Duration // the longest one command may run (the build timeout)
	ReapEvery   time.Duration // how often the reaper looks for expired VMs
}

// SandboxdConfig is what LoadSandboxd returns.
type SandboxdConfig struct {
	Sandboxd Sandboxd
}

// LoadSandboxd reads the settings for cmd/sandboxd.
func LoadSandboxd() (*SandboxdConfig, error) {
	r := &reader{}
	s := Sandboxd{
		ListenAddr:  r.required("SANDBOXD_LISTEN_ADDR"),
		Token:       r.required("SANDBOXD_TOKEN"),
		Driver:      r.required("SANDBOX_DRIVER"),
		MaxVMs:      r.integer("SANDBOX_MAX_PARALLEL_VMS", 4),
		CPUs:        r.integer("SANDBOX_VM_CPUS", 2),
		MemoryMB:    r.integer("SANDBOX_VM_MEMORY_MB", 4096),
		TimeLimit:   time.Duration(r.integer("SANDBOX_VM_TIME_LIMIT_SECONDS", 900)) * time.Second,
		ExecTimeout: time.Duration(r.integer("SANDBOX_BUILD_TIMEOUT_SECONDS", 600)) * time.Second,
		ReapEvery:   time.Duration(r.integer("SANDBOX_REAP_SECONDS", 10)) * time.Second,
	}
	if s.Driver != "" && s.Driver != "docker" {
		r.invalid = append(r.invalid, "SANDBOX_DRIVER must be docker (firecracker is not built yet)")
	}
	return &SandboxdConfig{Sandboxd: s}, r.err()
}
