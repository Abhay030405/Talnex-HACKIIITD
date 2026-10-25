package pipeline

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// ErrBusy means a job of this pipeline and target is still queued, running or retrying.
var ErrBusy = errors.New("this is still being checked; wait for it to finish")

// ErrBadStages is a plain-words problem with the chosen stages.
type ErrBadStages string

func (e ErrBadStages) Error() string { return string(e) }

type stageRow struct {
	name, runner string
	after        []string
	limit        int
}

// RunStages runs the chosen stages of a pipeline again for one target, as a new run. Every stage that is neither chosen
// nor after a chosen one is copied into the new run as done, with its last saved result (handlers read earlier results
// by run, see stage_result), so the chosen stages start at once and the stages after them chain as usual. A stage that
// has never finished cannot be reused and is run too. One transaction, under the same lock complete_job takes.
func RunStages(ctx context.Context, pool *pgxpool.Pool, pipeline, targetType, targetID string, chosen []string) (int, []string, error) {
	if len(chosen) == 0 {
		return 0, nil, ErrBadStages("choose at least one stage")
	}
	tx, err := pool.Begin(ctx)
	if err != nil {
		return 0, nil, err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1 || ':' || $2, 0))`, pipeline, targetID); err != nil {
		return 0, nil, err
	}

	rows, err := tx.Query(ctx, `SELECT stage, runner, after_stages, time_limit_seconds FROM pipeline_stages
		WHERE pipeline = $1 AND target_type = $2`, pipeline, targetType)
	if err != nil {
		return 0, nil, err
	}
	stages, err := pgx.CollectRows(rows, func(r pgx.CollectableRow) (stageRow, error) {
		var s stageRow
		return s, r.Scan(&s.name, &s.runner, &s.after, &s.limit)
	})
	if err != nil {
		return 0, nil, err
	}
	byName := map[string]stageRow{}
	for _, s := range stages {
		byName[s.name] = s
	}
	run := map[string]bool{}
	for _, c := range chosen {
		if _, ok := byName[c]; !ok {
			return 0, nil, ErrBadStages(fmt.Sprintf("%q is not a stage of %s", c, pipeline))
		}
		run[c] = true
	}

	var busy bool
	var last int
	if err := tx.QueryRow(ctx, `SELECT coalesce(bool_or(status IN ('queued', 'running', 'retrying')), false), coalesce(max(run_number), 0)
		FROM jobs WHERE pipeline = $1 AND target_type = $2 AND target_id = $3::uuid`, pipeline, targetType, targetID).Scan(&busy, &last); err != nil {
		return 0, nil, err
	}
	if busy {
		return 0, nil, ErrBusy
	}
	newRun := last + 1

	// The last saved result of every stage, from any earlier run.
	saved := map[string][]byte{}
	prev, err := tx.Query(ctx, `SELECT DISTINCT ON (job_type) job_type, result FROM jobs
		WHERE pipeline = $1 AND target_type = $2 AND target_id = $3::uuid AND status = 'done' AND result IS NOT NULL
		ORDER BY job_type, run_number DESC, updated_at DESC`, pipeline, targetType, targetID)
	if err != nil {
		return 0, nil, err
	}
	for prev.Next() {
		var name string
		var result []byte
		if err := prev.Scan(&name, &result); err != nil {
			prev.Close()
			return 0, nil, err
		}
		saved[name] = result
	}
	prev.Close()
	if err := prev.Err(); err != nil {
		return 0, nil, err
	}

	// Grow the set to run: everything after a chosen stage, and anything that has no saved result to reuse.
	for changed := true; changed; {
		changed = false
		for _, s := range stages {
			if run[s.name] {
				continue
			}
			needs := saved[s.name] == nil
			for _, a := range s.after {
				needs = needs || run[a]
			}
			if needs {
				run[s.name], changed = true, true
			}
		}
	}

	for _, s := range stages {
		if run[s.name] {
			continue
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO jobs (job_type, runner, target_type, target_id, input, pipeline, run_number, time_limit_seconds,
			                  status, result, dedupe_key)
			VALUES ($1, $2, $3, $4::uuid, '{}', $5, $6, $7, 'done', $8::jsonb || jsonb_build_object('reused_from_run', $9::int), $10)`,
			s.name, s.runner, targetType, targetID, pipeline, newRun, s.limit, string(saved[s.name]), last,
			fmt.Sprintf("%s:%s:%s:%s:%d", pipeline, s.name, targetType, targetID, newRun)); err != nil {
			return 0, nil, fmt.Errorf("reuse %s: %w", s.name, err)
		}
	}
	queued := []string{}
	for _, s := range stages {
		ready := run[s.name]
		for _, a := range s.after {
			ready = ready && !run[a]
		}
		if !ready {
			continue
		}
		if _, err := tx.Exec(ctx, `SELECT enqueue_job($1, $2, $3, $4::uuid, '{}', $5, $6, $7)`,
			s.name, s.runner, targetType, targetID, pipeline, newRun, s.limit); err != nil {
			return 0, nil, fmt.Errorf("queue %s: %w", s.name, err)
		}
		queued = append(queued, s.name)
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, nil, err
	}
	return newRun, queued, nil
}

// RetryFailed puts one failed job back in the queue for its own run. ok is false when the job is not failed.
func RetryFailed(ctx context.Context, pool *pgxpool.Pool, jobID string) (bool, error) {
	tag, err := pool.Exec(ctx, `UPDATE jobs SET status = 'queued', tries = 0, run_after = now(), error = NULL, updated_at = now()
		WHERE id = $1::uuid AND status = 'failed'`, jobID)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() == 1, nil
}
