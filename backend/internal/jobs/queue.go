// Package jobs is the Go side of the job queue. The rules (taking a job, retries, adding the next
// stage in the same step) live in Postgres functions, so Python and Go share one implementation.
package jobs

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	RunnerGo     = "go"
	RunnerPython = "python"
)

// Job is one row of the jobs table that a worker has taken.
type Job struct {
	ID         string
	Type       string
	Runner     string
	TargetType string
	TargetID   string
	Input      json.RawMessage
	Pipeline   *string
	RunNumber  int
	Tries      int
	MaxTries   int
	TimeLimit  time.Duration
}

// EnqueueParams describes one job to add. Zero values mean the database defaults.
type EnqueueParams struct {
	Type       string
	Runner     string
	TargetType string
	TargetID   string
	Input      any
	Pipeline   string
	RunNumber  int
	TimeLimit  time.Duration
	MaxTries   int
}

type Queue struct {
	pool *pgxpool.Pool
}

func NewQueue(pool *pgxpool.Pool) *Queue {
	return &Queue{pool: pool}
}

// Take locks and returns the next free job for a runner, or nil when there is none.
func (q *Queue) Take(ctx context.Context, runner, worker string) (*Job, error) {
	var (
		j         Job
		limitSecs int
	)
	err := q.pool.QueryRow(ctx, `
		SELECT id::text, job_type, runner, target_type, target_id::text, input, pipeline,
		       run_number, tries, max_tries, time_limit_seconds
		  FROM take_job($1, $2)`, runner, worker).
		Scan(&j.ID, &j.Type, &j.Runner, &j.TargetType, &j.TargetID, &j.Input, &j.Pipeline,
			&j.RunNumber, &j.Tries, &j.MaxTries, &limitSecs)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("take job: %w", err)
	}
	j.TimeLimit = time.Duration(limitSecs) * time.Second
	return &j, nil
}

// Complete saves the result, marks the job done and adds the next stages in one step.
// It returns the ids of the jobs it added.
func (q *Queue) Complete(ctx context.Context, jobID, worker string, result any) ([]string, error) {
	if result == nil {
		result = map[string]any{}
	}
	raw, err := json.Marshal(result)
	if err != nil {
		return nil, fmt.Errorf("encode job result: %w", err)
	}
	rows, err := q.pool.Query(ctx,
		`SELECT x::text FROM complete_job($1::uuid, $2, $3::jsonb) AS x`, jobID, worker, raw)
	if err != nil {
		return nil, fmt.Errorf("complete job: %w", err)
	}
	return collectStrings(rows)
}

// Fail records a failure. It returns the new status ("retrying" or "failed"),
// or "" when the worker no longer holds the job.
func (q *Queue) Fail(ctx context.Context, jobID, worker, message string, delay time.Duration) (string, error) {
	var status *string
	err := q.pool.QueryRow(ctx,
		`SELECT fail_job($1::uuid, $2, $3, $4)`, jobID, worker, message, int(delay.Seconds())).
		Scan(&status)
	if err != nil {
		return "", fmt.Errorf("fail job: %w", err)
	}
	if status == nil {
		return "", nil
	}
	return *status, nil
}

// Enqueue adds one job. It returns "" when the same job already exists.
func (q *Queue) Enqueue(ctx context.Context, p EnqueueParams) (string, error) {
	input := p.Input
	if input == nil {
		input = map[string]any{}
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return "", fmt.Errorf("encode job input: %w", err)
	}
	run := p.RunNumber
	if run == 0 {
		run = 1
	}
	limit := int(p.TimeLimit.Seconds())
	if limit == 0 {
		limit = 900
	}
	tries := p.MaxTries
	if tries == 0 {
		tries = 3
	}
	var pipeline *string
	if p.Pipeline != "" {
		pipeline = &p.Pipeline
	}
	var id *string
	err = q.pool.QueryRow(ctx,
		`SELECT enqueue_job($1, $2, $3, $4::uuid, $5::jsonb, $6, $7, $8, $9)::text`,
		p.Type, p.Runner, p.TargetType, p.TargetID, raw, pipeline, run, limit, tries).Scan(&id)
	if err != nil {
		return "", fmt.Errorf("enqueue job: %w", err)
	}
	if id == nil {
		return "", nil
	}
	return *id, nil
}

// StartPipeline adds every first stage of a pipeline for a target.
func (q *Queue) StartPipeline(ctx context.Context, pipeline, targetType, targetID string, run int) ([]string, error) {
	if run == 0 {
		run = 1
	}
	rows, err := q.pool.Query(ctx,
		`SELECT x::text FROM start_pipeline($1, $2, $3::uuid, $4) AS x`, pipeline, targetType, targetID, run)
	if err != nil {
		return nil, fmt.Errorf("start pipeline: %w", err)
	}
	return collectStrings(rows)
}

// ReapStuck fails jobs that ran past their time limit. It returns how many it handled.
func (q *Queue) ReapStuck(ctx context.Context) (int, error) {
	var n int
	if err := q.pool.QueryRow(ctx, `SELECT reap_stuck_jobs()`).Scan(&n); err != nil {
		return 0, fmt.Errorf("reap stuck jobs: %w", err)
	}
	return n, nil
}

func collectStrings(rows pgx.Rows) ([]string, error) {
	defer rows.Close()
	var out []string
	for rows.Next() {
		var s string
		if err := rows.Scan(&s); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, rows.Err()
}
