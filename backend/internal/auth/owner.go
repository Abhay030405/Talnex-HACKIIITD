package auth

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Every function below answers "is this thing owned by this user?". A thing that does not exist
// and a thing owned by someone else both answer false, so the API can reply "not found" to both
// and never reveal that something exists.

func OwnsEvent(ctx context.Context, pool *pgxpool.Pool, userID, eventID string) (bool, error) {
	return exists(ctx, pool,
		`SELECT EXISTS (SELECT 1 FROM events WHERE id = $2::uuid AND owner_id = $1::uuid)`, userID, eventID)
}

func OwnsProject(ctx context.Context, pool *pgxpool.Pool, userID, projectID string) (bool, error) {
	return exists(ctx, pool, `
		SELECT EXISTS (SELECT 1 FROM projects p JOIN events e ON e.id = p.event_id
		                WHERE p.id = $2::uuid AND e.owner_id = $1::uuid)`, userID, projectID)
}

func OwnsCandidate(ctx context.Context, pool *pgxpool.Pool, userID, candidateID string) (bool, error) {
	return exists(ctx, pool,
		`SELECT EXISTS (SELECT 1 FROM candidates WHERE id = $2::uuid AND owner_id = $1::uuid)`, userID, candidateID)
}

func OwnsCandidateProject(ctx context.Context, pool *pgxpool.Pool, userID, candidateProjectID string) (bool, error) {
	return exists(ctx, pool, `
		SELECT EXISTS (SELECT 1 FROM candidate_projects cp JOIN candidates c ON c.id = cp.candidate_id
		                WHERE cp.id = $2::uuid AND c.owner_id = $1::uuid)`, userID, candidateProjectID)
}

func exists(ctx context.Context, pool *pgxpool.Pool, query string, args ...any) (bool, error) {
	var ok bool
	if err := pool.QueryRow(ctx, query, args...).Scan(&ok); err != nil {
		// A badly formed id is "not found", not a server error.
		if isInvalidUUID(err) {
			return false, nil
		}
		return false, err
	}
	return ok, nil
}
