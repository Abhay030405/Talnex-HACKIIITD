// Command migrate applies the database migrations in backend/migrations and then stops.
// Go owns the schema; nothing else changes table shapes.
package main

import (
	"errors"
	"fmt"
	"os"
	"strings"

	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/pgx/v5"
	_ "github.com/golang-migrate/migrate/v4/source/file"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/config"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "migrate failed:", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := config.LoadMigrate()
	if err != nil {
		return err
	}
	// golang-migrate picks the database driver from the address scheme.
	dbURL := strings.Replace(cfg.Database.URL, "postgres://", "pgx5://", 1)
	dbURL = strings.Replace(dbURL, "postgresql://", "pgx5://", 1)

	m, err := migrate.New("file://"+cfg.Migrate.Dir, dbURL)
	if err != nil {
		return err
	}
	defer m.Close()

	err = m.Up()
	switch {
	case errors.Is(err, migrate.ErrNoChange):
		fmt.Println("database is up to date")
		return nil
	case err != nil:
		return err
	}
	version, dirty, _ := m.Version()
	fmt.Printf("migrated to version %d (dirty=%v)\n", version, dirty)
	return nil
}
