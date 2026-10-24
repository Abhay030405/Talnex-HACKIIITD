// Command sandboxd is the VM host daemon (architecture section 28). It runs on the sandbox host, never reads the
// database or any TalNex key, and answers only calls that carry its token.
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/config"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd/api"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd/drivers"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd/reaper"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "sandboxd stopped:", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := config.LoadSandboxd()
	if err != nil {
		return err
	}
	s := cfg.Sandboxd
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	drv := drivers.NewDocker() // SANDBOX_DRIVER is checked to be "docker" by the loader
	m := sandboxd.NewManager(drv, sandboxd.Limits{
		MaxVMs: s.MaxVMs, CPUs: s.CPUs, MemoryMB: s.MemoryMB, TimeLimit: s.TimeLimit, ExecTimeout: s.ExecTimeout,
	})

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := m.Ping(ctx); err != nil {
		return fmt.Errorf("the docker engine is not answering (is Docker running?): %w", err)
	}
	// VMs are per-run and never reused: anything left by an earlier run of this daemon is destroyed.
	if n, err := m.DestroyAll(ctx); err != nil {
		return fmt.Errorf("clean up old VMs: %w", err)
	} else if n > 0 {
		log.Info("destroyed VMs left over from an earlier run", "count", n)
	}
	go reaper.Run(ctx, m, s.ReapEvery, log)

	srv := &http.Server{
		Addr:              s.ListenAddr,
		Handler:           api.NewHandler(m, s.Driver, s.Token, log),
		ReadHeaderTimeout: 10 * time.Second,
	}
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdown)
		if n, _ := m.DestroyAll(shutdown); n > 0 {
			log.Info("destroyed VMs at shutdown", "count", n)
		}
	}()

	log.Info("sandboxd started", "addr", s.ListenAddr, "driver", s.Driver, "max_vms", s.MaxVMs)
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}
