// Package reaper destroys VMs that have run past their time limit, so a crashed worker never leaves one running.
package reaper

import (
	"context"
	"log/slog"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd"
)

// Run looks for expired VMs every `every` until ctx ends.
func Run(ctx context.Context, m *sandboxd.Manager, every time.Duration, log *slog.Logger) {
	if log == nil {
		log = slog.Default()
	}
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			if n := m.Reap(ctx); n > 0 {
				log.Info("reaper destroyed expired VMs", "count", n)
			}
		}
	}
}
