// Package dbtest gives integration tests a database. Tests are skipped when
// TALNEX_TEST_DATABASE_URL is not set, so `go test ./...` always works without Docker.
// Use a separate database (for example talnex_test): tests empty the jobs table.
package dbtest

import (
	"context"
	"os"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
)

func Pool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	url := os.Getenv("TALNEX_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("TALNEX_TEST_DATABASE_URL is not set")
	}
	pool, err := pgxpool.New(context.Background(), url)
	if err != nil {
		t.Fatalf("open test database: %v", err)
	}
	t.Cleanup(pool.Close)
	if err := pool.Ping(context.Background()); err != nil {
		t.Fatalf("test database does not answer: %v", err)
	}
	return pool
}
