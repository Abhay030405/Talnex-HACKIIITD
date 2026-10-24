package pipeline

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/codeforces"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
)

// profileSignal is the name of the one row this stage keeps per candidate in coding_signals.
const profileSignal = "codeforces_profile"

// skippedSignal is one row per contest where all contest submissions were Skipped (architecture section 18).
const skippedSignal = "codeforces_all_skipped"

// problemSkippedSignal is one row per problem Skipped in a contest that was otherwise judged. Weight "medium" when no
// later resubmission explains it, "not_suspicious" when one does. Codeforces gives no reason, so it is a hint only.
const problemSkippedSignal = "codeforces_problem_skipped"

// Codeforces is the Codeforces part of the "coding profiles" stage (architecture sections 8 and 18). It reads the
// public profile from the official API and keeps the facts (rating, rank, contests, solved problems, last activity)
// as one row in coding_signals. The row is evidence only: weight "not_suspicious", never a verdict. A handle that does
// not exist ends as "found: false" and is never a mark against the candidate. Running it twice replaces the row.
func Codeforces(pool *pgxpool.Pool, cf *codeforces.Client) jobs.Handler {
	return func(ctx context.Context, job *jobs.Job) (map[string]any, error) {
		if job.TargetType != "candidate" {
			return nil, fmt.Errorf("codeforces works on a candidate, not a %q", job.TargetType)
		}
		var handle *string
		err := pool.QueryRow(ctx, `SELECT coding_handles->>'codeforces' FROM candidates WHERE id = $1::uuid`, job.TargetID).Scan(&handle)
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, fmt.Errorf("candidate %s does not exist", job.TargetID)
		}
		if err != nil {
			return nil, fmt.Errorf("find Codeforces handle: %w", err)
		}
		if handle == nil || strings.TrimSpace(*handle) == "" {
			return map[string]any{"skipped": true, "reason": "no Codeforces handle given"}, nil
		}
		h := strings.TrimSpace(*handle)

		sig, err := cf.Fetch(ctx, h)
		if errors.Is(err, codeforces.ErrNotFound) {
			return map[string]any{"found": false, "handle": h, "reason": "Codeforces has no user with this handle"}, nil
		}
		if err != nil {
			return nil, err // a rate limit or a network problem: the queue tries again later
		}
		if err := saveProfile(ctx, pool, job.TargetID, sig); err != nil {
			return nil, err
		}
		return map[string]any{
			"all_skipped_contests": len(sig.AllSkipped), "partly_skipped_problems": len(sig.PartlySkipped),
			"found":                true, "handle": sig.Handle, "rating": sig.Rating, "max_rating": sig.MaxRating, "rank": sig.Rank,
			"contests": sig.Contests, "solved_problems": sig.SolvedProblems, "recent_activity": sig.RecentActivity,
		}, nil
	}
}

// saveProfile replaces the candidate's Codeforces profile row in one step, so a second run leaves exactly one row.
func saveProfile(ctx context.Context, pool *pgxpool.Pool, candidateID string, sig codeforces.Signals) error {
	evidence, err := json.Marshal(sig)
	if err != nil {
		return err
	}
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	if _, err := tx.Exec(ctx, `DELETE FROM coding_signals WHERE candidate_id = $1::uuid AND site = 'codeforces' AND signal = $2`,
		candidateID, profileSignal); err != nil {
		return fmt.Errorf("clear old Codeforces profile: %w", err)
	}
	if _, err := tx.Exec(ctx, `INSERT INTO coding_signals (candidate_id, site, signal, weight, evidence)
		VALUES ($1::uuid, 'codeforces', $2, 'not_suspicious', $3::jsonb)`, candidateID, profileSignal, string(evidence)); err != nil {
		return fmt.Errorf("save Codeforces profile: %w", err)
	}
	if _, err := tx.Exec(ctx, `DELETE FROM coding_signals WHERE candidate_id = $1::uuid AND site = 'codeforces' AND signal = $2`,
		candidateID, skippedSignal); err != nil {
		return fmt.Errorf("clear old all-skipped signals: %w", err)
	}
	for _, c := range sig.AllSkipped {
		ev, _ := json.Marshal(c)
		if _, err := tx.Exec(ctx, `INSERT INTO coding_signals (candidate_id, site, contest, signal, weight, evidence)
			VALUES ($1::uuid, 'codeforces', $2, $3, 'strong', $4::jsonb)`, candidateID, c.ContestName, skippedSignal, string(ev)); err != nil {
			return fmt.Errorf("save all-skipped signal: %w", err)
		}
	}
	if _, err := tx.Exec(ctx, `DELETE FROM coding_signals WHERE candidate_id = $1::uuid AND site = 'codeforces' AND signal = $2`,
		candidateID, problemSkippedSignal); err != nil {
		return fmt.Errorf("clear old problem-skipped signals: %w", err)
	}
	for _, p := range sig.PartlySkipped {
		weight := "medium"
		if p.Resubmitted {
			weight = "not_suspicious"
		}
		ev, _ := json.Marshal(p)
		if _, err := tx.Exec(ctx, `INSERT INTO coding_signals (candidate_id, site, contest, problem, signal, weight, evidence)
			VALUES ($1::uuid, 'codeforces', $2, $3, $4, $5, $6::jsonb)`, candidateID, p.ContestName, p.Problem, problemSkippedSignal,
			weight, string(ev)); err != nil {
			return fmt.Errorf("save problem-skipped signal: %w", err)
		}
	}
	return tx.Commit(ctx)
}
