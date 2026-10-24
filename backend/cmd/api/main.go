// Command api starts the public API server.
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

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/cleanup"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/config"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db"
	apihttp "github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/http"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/live"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/storage/r2"
)

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	if err := run(log); err != nil {
		log.Error("api stopped", "err", err)
		os.Exit(1)
	}
}

func run(log *slog.Logger) error {
	cfg, err := config.LoadAPI()
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
		PublicEndpoint: cfg.Storage.PublicEndpoint,
	})
	if err != nil {
		return err
	}
	if err := store.EnsureBucket(ctx); err != nil {
		return err
	}

	// The live view: one listening connection for the whole process, and an hourly clean-up of old saved events.
	hub := live.NewHub(pool, log)
	go hub.Run(ctx)
	go func() {
		tick := time.NewTicker(time.Hour)
		defer tick.Stop()
		for {
			if n, err := cleanup.PurgeOldLiveEvents(ctx, pool, cleanup.LiveEventsKeepFor); err != nil {
				log.Warn("live events clean-up", "err", err)
			} else if n > 0 {
				log.Info("live events clean-up", "deleted", n)
			}
			select {
			case <-ctx.Done():
				return
			case <-tick.C:
			}
		}
	}()

	handler := apihttp.NewHandler(apihttp.Options{
		Pool:               pool,
		AuthSecret:         cfg.API.AuthSecret,
		WebOrigin:          cfg.API.WebOrigin,
		EnableDevEndpoints: cfg.API.EnableDevEndpoints,
		SMSGatewayKey:      cfg.API.SMSGatewayKey,
		Log:                log,
		Files:              store,
		ProofLinks:         store,
		FileRemover:        store,
		Walkthrough:        apihttp.WalkthroughLimits(cfg.API.Walkthrough),
		Tour:               apihttp.TourLimits(cfg.API.Tour),
		Live:               hub,
		Ready: func(ctx context.Context) error {
			if err := pool.Ping(ctx); err != nil {
				return fmt.Errorf("database: %w", err)
			}
			return store.EnsureBucket(ctx)
		},
	})

	srv := &http.Server{
		Addr:              fmt.Sprintf(":%d", cfg.API.Port),
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
	}

	errc := make(chan error, 1)
	go func() {
		log.Info("api listening", "addr", srv.Addr)
		errc <- srv.ListenAndServe()
	}()

	select {
	case err := <-errc:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
	case <-ctx.Done():
		log.Info("shutting down")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		return srv.Shutdown(shutdownCtx)
	}
	return nil
}
