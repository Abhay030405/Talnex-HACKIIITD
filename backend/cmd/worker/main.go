// Command worker starts the Go job workers (GitHub data, Codeforces, cleanup, and the Go self-test step).
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/codeforces"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/config"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/storage/r2"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	if err := run(log); err != nil {
		log.Error("worker stopped", "err", err)
		os.Exit(1)
	}
}

func run(log *slog.Logger) error {
	cfg, err := config.LoadWorker()
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	pool, err := db.Connect(ctx, cfg.Database.URL)
	if err != nil {
		return err
	}
	defer pool.Close()

	store, err := r2.New(r2.Options{
		Endpoint: cfg.Storage.Endpoint, Region: cfg.Storage.Region, Bucket: cfg.Storage.Bucket,
		AccessKey: cfg.Storage.AccessKey, SecretKey: cfg.Storage.SecretKey, ViewLinkTTL: cfg.Storage.ViewLinkTTL,
	})
	if err != nil {
		return err
	}

	host, _ := os.Hostname()
	worker := &jobs.Worker{
		Queue:        jobs.NewQueue(pool),
		Pool:         pool,
		Runner:       jobs.RunnerGo,
		ID:           fmt.Sprintf("go-%s-%d", host, os.Getpid()),
		Handlers:     pipeline.GoHandlers(pool, github.NewClient(cfg.GitHub.BaseURL, cfg.GitHub.Token), codeforces.NewClient(cfg.Codeforces.BaseURL), store, pipeline.HistoryLimits(cfg.GitHub.History)),
		Concurrency:  cfg.Worker.Concurrency,
		PollInterval: cfg.Worker.PollInterval,
		// The Go worker also fails jobs that ran past their time limit, for both runners.
		ReapInterval: cfg.Worker.ReapInterval,
		RetryDelay:   cfg.Worker.RetryDelay,
		Log:          log,
	}

	// A tiny health address so Docker can tell the worker is alive.
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		pingCtx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()
		if err := pool.Ping(pingCtx); err != nil {
			http.Error(w, `{"status":"database down"}`, http.StatusServiceUnavailable)
			return
		}
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	health := &http.Server{Addr: fmt.Sprintf(":%d", cfg.Worker.HealthPort), Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go func() {
		if err := health.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Error("health server stopped", "err", err)
		}
	}()
	defer health.Close()

	log.Info("go worker started", "id", worker.ID, "concurrency", worker.Concurrency)
	worker.Run(ctx)
	log.Info("go worker stopped")
	return nil
}
