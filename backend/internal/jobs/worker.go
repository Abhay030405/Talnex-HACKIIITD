package jobs

import (
	"context"
	"fmt"
	"log/slog"
	"runtime/debug"
	"sync"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Handler runs one job. Its result is saved with the job. A handler with nothing to do
// returns {"skipped": true, "reason": "..."} so the next stages still start.
type Handler func(ctx context.Context, job *Job) (map[string]any, error)

// Worker takes jobs of one runner and runs them with the registered handlers.
type Worker struct {
	Queue        *Queue
	Pool         *pgxpool.Pool
	Runner       string
	ID           string
	Handlers     map[string]Handler
	Concurrency  int
	PollInterval time.Duration
	ReapInterval time.Duration // 0 = this worker does not reap stuck jobs
	RetryDelay   time.Duration
	Log          *slog.Logger
}

// Run works until ctx is cancelled, then waits for running jobs to stop.
func (w *Worker) Run(ctx context.Context) {
	if w.Concurrency < 1 {
		w.Concurrency = 1
	}
	if w.PollInterval <= 0 {
		w.PollInterval = 5 * time.Second
	}
	if w.RetryDelay <= 0 {
		w.RetryDelay = 30 * time.Second
	}
	if w.Log == nil {
		w.Log = slog.Default()
	}

	wake := make(chan struct{}, w.Concurrency)
	var wg sync.WaitGroup

	wg.Add(1)
	go func() {
		defer wg.Done()
		w.listen(ctx, wake)
	}()

	if w.ReapInterval > 0 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			w.reapLoop(ctx)
		}()
	}

	for i := 0; i < w.Concurrency; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			w.loop(ctx, fmt.Sprintf("%s-%d", w.ID, n), wake)
		}(i)
	}
	wg.Wait()
}

func (w *Worker) loop(ctx context.Context, worker string, wake <-chan struct{}) {
	ticker := time.NewTicker(w.PollInterval)
	defer ticker.Stop()
	for ctx.Err() == nil {
		job, err := w.Queue.Take(ctx, w.Runner, worker)
		if err != nil {
			if ctx.Err() == nil {
				w.Log.Error("take job failed", "err", err)
			}
		} else if job != nil {
			w.run(ctx, worker, job)
			continue // look for more work straight away
		}
		select {
		case <-ctx.Done():
			return
		case <-wake:
		case <-ticker.C:
		}
	}
}

func (w *Worker) run(ctx context.Context, worker string, job *Job) {
	log := w.Log.With("job", job.ID, "type", job.Type, "target", job.TargetID, "try", job.Tries)
	// Reporting the outcome must work even while we are shutting down.
	report := context.WithoutCancel(ctx)

	handler, ok := w.Handlers[job.Type]
	if !ok {
		w.fail(report, log, worker, job, fmt.Errorf("no handler for job type %q", job.Type))
		return
	}

	runCtx, cancel := context.WithTimeout(ctx, job.TimeLimit)
	defer cancel()

	started := time.Now()
	w.emitLive(report, job, "stage.started", map[string]any{"try_number": job.Tries})
	result, err := safeCall(runCtx, handler, job)
	if err == nil && runCtx.Err() != nil {
		err = fmt.Errorf("stopped before finishing: %w", runCtx.Err())
	}
	if err != nil {
		w.fail(report, log, worker, job, err)
		return
	}

	next, err := w.Queue.Complete(report, job.ID, worker, result)
	if err != nil {
		log.Error("could not save job result", "err", err)
		return
	}
	skipped, _ := result["skipped"].(bool)
	w.emitLive(report, job, "stage.finished", map[string]any{"seconds": time.Since(started).Round(100 * time.Millisecond).Seconds(),
		"skipped": skipped, "reason": result["reason"], "summary": summaryOf(result)})
	log.Info("job done", "took", time.Since(started).Round(time.Millisecond), "next_jobs", len(next))
}

func (w *Worker) fail(ctx context.Context, log *slog.Logger, worker string, job *Job, cause error) {
	status, err := w.Queue.Fail(ctx, job.ID, worker, cause.Error(), w.RetryDelay)
	if err != nil {
		log.Error("could not record job failure", "err", err, "cause", cause)
		return
	}
	log.Warn("job failed", "status", status, "err", cause)
	msg := cause.Error()
	if len(msg) > 300 {
		msg = msg[:300]
	}
	w.emitLive(ctx, job, "stage.failed", map[string]any{"status": status, "error": msg})
}

func safeCall(ctx context.Context, h Handler, job *Job) (res map[string]any, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("handler panicked: %v\n%s", r, debug.Stack())
		}
	}()
	return h(ctx, job)
}

// listen wakes the loops the moment a job for this runner is added.
func (w *Worker) listen(ctx context.Context, wake chan<- struct{}) {
	for ctx.Err() == nil {
		if err := w.listenOnce(ctx, wake); err != nil && ctx.Err() == nil {
			w.Log.Warn("job wake-up listener stopped, will retry", "err", err)
			select {
			case <-ctx.Done():
			case <-time.After(3 * time.Second):
			}
		}
	}
}

func (w *Worker) listenOnce(ctx context.Context, wake chan<- struct{}) error {
	conn, err := w.Pool.Acquire(ctx)
	if err != nil {
		return err
	}
	defer conn.Release()
	if _, err := conn.Exec(ctx, "LISTEN jobs"); err != nil {
		return err
	}
	for {
		n, err := conn.Conn().WaitForNotification(ctx)
		if err != nil {
			return err
		}
		if n.Payload != w.Runner {
			continue
		}
		select {
		case wake <- struct{}{}:
		default: // enough wake-ups already waiting
		}
	}
}

func (w *Worker) reapLoop(ctx context.Context) {
	ticker := time.NewTicker(w.ReapInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			n, err := w.Queue.ReapStuck(ctx)
			if err != nil && ctx.Err() == nil {
				w.Log.Error("reap stuck jobs failed", "err", err)
			} else if n > 0 {
				w.Log.Warn("failed jobs that ran past their time limit", "count", n)
			}
		}
	}
}
