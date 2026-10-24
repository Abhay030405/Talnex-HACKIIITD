package pipeline

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/storage/r2"
)

// StageResumeCleanup is the last stage of the recruiter_report pipeline (architecture section 23).
const StageResumeCleanup = "resume_cleanup"

// RecruiterReport builds the candidate's proof report and then removes the resume and personal details.
const RecruiterReport = "recruiter_report"

// PrefixDeleter is the part of file storage the cleanup needs. The r2 Store does this.
type PrefixDeleter interface {
	DeletePrefix(ctx context.Context, prefix string) error
}

// ResumeCleanup deletes the resume file and everything stored under the candidate's resume folder, forgets the
// file key, empties the project bullets, and ends the candidate as done (or done_with_gaps when the report says
// something could not be tested). It runs only when the report exists, so a failed report never loses the resume.
// Running it twice is safe: the second run finds nothing left to delete and sets the same values.
func ResumeCleanup(pool *pgxpool.Pool, files PrefixDeleter) jobs.Handler {
	return func(ctx context.Context, job *jobs.Job) (map[string]any, error) {
		if job.TargetType != "candidate" {
			return nil, fmt.Errorf("resume cleanup works on a candidate, not a %q", job.TargetType)
		}
		var hasGaps bool
		err := pool.QueryRow(ctx, `SELECT has_gaps FROM candidate_reports WHERE candidate_id = $1::uuid`, job.TargetID).Scan(&hasGaps)
		if err == pgx.ErrNoRows {
			return nil, fmt.Errorf("the report for candidate %s is not saved yet; the resume is kept", job.TargetID)
		}
		if err != nil {
			return nil, fmt.Errorf("find report: %w", err)
		}

		// Files first: if this fails the queue tries again and the database still says the resume exists.
		if files == nil {
			return nil, fmt.Errorf("file storage is not set up; the resume is kept")
		}
		if err := files.DeletePrefix(ctx, r2.ResumePrefix(job.TargetID)); err != nil {
			return nil, fmt.Errorf("delete resume files: %w", err)
		}

		status := "done"
		if hasGaps {
			status = "done_with_gaps"
		}
		tx, err := pool.Begin(ctx)
		if err != nil {
			return nil, err
		}
		defer func() { _ = tx.Rollback(ctx) }()
		if _, err := tx.Exec(ctx, `
			UPDATE candidates
			   SET resume_key = NULL,
			       resume_deleted_at = COALESCE(resume_deleted_at, now()),
			       status = $2, status_detail = NULL, updated_at = now()
			 WHERE id = $1::uuid`, job.TargetID, status); err != nil {
			return nil, fmt.Errorf("clear resume details: %w", err)
		}
		if _, err := tx.Exec(ctx, `UPDATE candidate_projects SET bullets = '{}' WHERE candidate_id = $1::uuid`, job.TargetID); err != nil {
			return nil, fmt.Errorf("clear project bullets: %w", err)
		}
		if err := tx.Commit(ctx); err != nil {
			return nil, err
		}
		return map[string]any{"status": status, "resume_deleted": true}, nil
	}
}
