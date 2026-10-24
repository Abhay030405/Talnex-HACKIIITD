package auth

import (
	"errors"

	"github.com/jackc/pgx/v5/pgconn"
)

// 22P02 = invalid_text_representation, which Postgres raises for a malformed uuid.
func isInvalidUUID(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "22P02"
}
