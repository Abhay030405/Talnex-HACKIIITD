package jobs_test

import (
	"context"
	"crypto/rand"
	"fmt"
	"io"
	"log/slog"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
)

func newID() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}

func count(t *testing.T, pool *pgxpool.Pool, target, jobType string) int {
	t.Helper()
	var n int
	err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM jobs WHERE target_id = $1::uuid AND job_type = $2`, target, jobType).Scan(&n)
	if err != nil {
		t.Fatal(err)
	}
	return n
}

func status(t *testing.T, pool *pgxpool.Pool, target, jobType string) string {
	t.Helper()
	var s string
	err := pool.QueryRow(context.Background(),
		`SELECT status FROM jobs WHERE target_id = $1::uuid AND job_type = $2`, target, jobType).Scan(&s)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

// markRunning puts a specific job in the running state for a worker, as Take would.
func markRunning(t *testing.T, pool *pgxpool.Pool, jobID, worker string) {
	t.Helper()
	_, err := pool.Exec(context.Background(),
		`UPDATE jobs SET status='running', tries=tries+1, locked_by=$2, locked_at=now() WHERE id=$1::uuid`, jobID, worker)
	if err != nil {
		t.Fatal(err)
	}
}

func TestSelfTestChainHopsBetweenRunners(t *testing.T) {
	pool := dbtest.Pool(t)
	ctx := context.Background()
	q := jobs.NewQueue(pool)
	target := newID()

	started, err := q.StartPipeline(ctx, "selftest", "project", target, 1)
	if err != nil || len(started) != 1 {
		t.Fatalf("start: %v %v", started, err)
	}

	// Only the Python stage is free; the Go stage waits behind it.
	if j, _ := q.Take(ctx, jobs.RunnerGo, "wg"); j != nil && j.TargetID == target {
		t.Fatal("go stage must not be free before the python stage is done")
	}
	a := takeFor(t, q, jobs.RunnerPython, "wp", target)
	if a.Type != "selftest_a" {
		t.Fatalf("first stage = %s", a.Type)
	}
	next, err := q.Complete(ctx, a.ID, "wp", map[string]any{"ok": true})
	if err != nil || len(next) != 1 {
		t.Fatalf("complete a: %v %v", next, err)
	}
	b := takeFor(t, q, jobs.RunnerGo, "wg", target)
	if b.Type != "selftest_b" {
		t.Fatalf("second stage = %s", b.Type)
	}
	if _, err := q.Complete(ctx, b.ID, "wg", nil); err != nil {
		t.Fatal(err)
	}
	c := takeFor(t, q, jobs.RunnerPython, "wp", target)
	if c.Type != "selftest_c" {
		t.Fatalf("third stage = %s", c.Type)
	}
}

// takeFor takes jobs until it finds the one for target (other tests' leftovers are put back as failed).
func takeFor(t *testing.T, q *jobs.Queue, runner, worker, target string) *jobs.Job {
	t.Helper()
	for i := 0; i < 20; i++ {
		j, err := q.Take(context.Background(), runner, worker)
		if err != nil {
			t.Fatal(err)
		}
		if j == nil {
			break
		}
		if j.TargetID == target {
			return j
		}
	}
	t.Fatalf("no %s job for target %s", runner, target)
	return nil
}

func TestStartPipelineTwiceAddsNothingNew(t *testing.T) {
	pool := dbtest.Pool(t)
	q := jobs.NewQueue(pool)
	target := newID()
	first, _ := q.StartPipeline(context.Background(), "selftest", "project", target, 1)
	second, _ := q.StartPipeline(context.Background(), "selftest", "project", target, 1)
	if len(first) != 1 || len(second) != 0 {
		t.Fatalf("first=%d second=%d", len(first), len(second))
	}
	// A re-run is a new run number, so it gets its own jobs.
	rerun, _ := q.StartPipeline(context.Background(), "selftest", "project", target, 2)
	if len(rerun) != 1 {
		t.Fatalf("rerun=%d", len(rerun))
	}
}

// The hackathon stage project_score waits for four stages. When they finish at the same moment,
// it must be added exactly once, never zero times and never twice.
func TestStageWithSeveralPredecessorsStartsExactlyOnce(t *testing.T) {
	pool := dbtest.Pool(t)
	ctx := context.Background()
	q := jobs.NewQueue(pool)

	for round := 0; round < 25; round++ {
		target := newID()
		var ids []string
		for _, stage := range []string{"feature_score", "repo_checks", "tutorial_copy", "authorship_read"} {
			id, err := q.Enqueue(ctx, jobs.EnqueueParams{
				Type: stage, Runner: jobs.RunnerPython, TargetType: "project", TargetID: target, Pipeline: "hackathon",
			})
			if err != nil || id == "" {
				t.Fatalf("enqueue %s: %v", stage, err)
			}
			markRunning(t, pool, id, "w")
			ids = append(ids, id)
		}

		var wg sync.WaitGroup
		for _, id := range ids {
			wg.Add(1)
			go func(id string) {
				defer wg.Done()
				if _, err := q.Complete(ctx, id, "w", nil); err != nil {
					t.Error(err)
				}
			}(id)
		}
		wg.Wait()

		if n := count(t, pool, target, "project_score"); n != 1 {
			t.Fatalf("round %d: project_score added %d times, want 1", round, n)
		}
	}
}

func TestStageWaitsUntilEveryPredecessorIsDone(t *testing.T) {
	pool := dbtest.Pool(t)
	ctx := context.Background()
	q := jobs.NewQueue(pool)
	target := newID()

	var ids []string
	for _, stage := range []string{"feature_score", "repo_checks", "tutorial_copy", "authorship_read"} {
		id, _ := q.Enqueue(ctx, jobs.EnqueueParams{
			Type: stage, Runner: jobs.RunnerPython, TargetType: "project", TargetID: target, Pipeline: "hackathon"})
		markRunning(t, pool, id, "w")
		ids = append(ids, id)
	}
	for i, id := range ids[:3] {
		if _, err := q.Complete(ctx, id, "w", nil); err != nil {
			t.Fatal(err)
		}
		if n := count(t, pool, target, "project_score"); n != 0 {
			t.Fatalf("after %d of 4 predecessors, project_score already added", i+1)
		}
	}
	if _, err := q.Complete(ctx, ids[3], "w", nil); err != nil {
		t.Fatal(err)
	}
	if n := count(t, pool, target, "project_score"); n != 1 {
		t.Fatalf("project_score added %d times", n)
	}
}

func TestCompleteByAnotherWorkerIsIgnored(t *testing.T) {
	pool := dbtest.Pool(t)
	ctx := context.Background()
	q := jobs.NewQueue(pool)
	target := newID()
	id, _ := q.Enqueue(ctx, jobs.EnqueueParams{
		Type: "selftest_a", Runner: jobs.RunnerPython, TargetType: "project", TargetID: target, Pipeline: "selftest"})
	markRunning(t, pool, id, "owner")

	next, err := q.Complete(ctx, id, "someone-else", nil)
	if err != nil || len(next) != 0 {
		t.Fatalf("got %v %v", next, err)
	}
	if s := status(t, pool, target, "selftest_a"); s != "running" {
		t.Fatalf("status = %s, a stranger must not finish the job", s)
	}
}

func TestFailRetriesThenGivesUp(t *testing.T) {
	pool := dbtest.Pool(t)
	ctx := context.Background()
	q := jobs.NewQueue(pool)
	target := newID()
	id, _ := q.Enqueue(ctx, jobs.EnqueueParams{
		Type: "selftest_a", Runner: jobs.RunnerPython, TargetType: "project", TargetID: target, MaxTries: 2})

	markRunning(t, pool, id, "w")
	if s, _ := q.Fail(ctx, id, "w", "first", 0); s != "retrying" {
		t.Fatalf("after try 1 status = %q", s)
	}
	markRunning(t, pool, id, "w")
	if s, _ := q.Fail(ctx, id, "w", "second", 0); s != "failed" {
		t.Fatalf("after try 2 status = %q", s)
	}
}

func TestReapFailsJobsPastTheirTimeLimit(t *testing.T) {
	pool := dbtest.Pool(t)
	ctx := context.Background()
	q := jobs.NewQueue(pool)
	target := newID()
	id, _ := q.Enqueue(ctx, jobs.EnqueueParams{
		Type: "selftest_a", Runner: jobs.RunnerPython, TargetType: "project", TargetID: target, TimeLimit: 10 * time.Second})
	markRunning(t, pool, id, "crashed")
	if _, err := pool.Exec(ctx, `UPDATE jobs SET locked_at = now() - interval '5 minutes' WHERE id = $1::uuid`, id); err != nil {
		t.Fatal(err)
	}
	n, err := q.ReapStuck(ctx)
	if err != nil || n < 1 {
		t.Fatalf("reaped %d, err %v", n, err)
	}
	if s := status(t, pool, target, "selftest_a"); s != "retrying" {
		t.Fatalf("status = %s", s)
	}
}

// Two workers (one per runner) run the whole selftest pipeline. The poll interval is long,
// so finishing fast proves the wake-up signal works.
func TestWorkersRunPipelineAndWakeUpFast(t *testing.T) {
	pool := dbtest.Pool(t)
	if _, err := pool.Exec(context.Background(), `DELETE FROM jobs`); err != nil {
		t.Fatal(err)
	}
	q := jobs.NewQueue(pool)
	log := slog.New(slog.NewTextHandler(io.Discard, nil))

	pyHandlers := map[string]jobs.Handler{
		"selftest_a": func(context.Context, *jobs.Job) (map[string]any, error) { return map[string]any{"a": 1}, nil },
		"selftest_c": func(context.Context, *jobs.Job) (map[string]any, error) { return map[string]any{"c": 1}, nil },
	}
	goHandlers := map[string]jobs.Handler{
		"selftest_b": func(context.Context, *jobs.Job) (map[string]any, error) { return map[string]any{"b": 1}, nil },
	}

	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup
	for _, w := range []*jobs.Worker{
		{Queue: q, Pool: pool, Runner: jobs.RunnerPython, ID: "tp", Handlers: pyHandlers, Concurrency: 2, PollInterval: time.Minute, Log: log},
		{Queue: q, Pool: pool, Runner: jobs.RunnerGo, ID: "tg", Handlers: goHandlers, Concurrency: 2, PollInterval: time.Minute, Log: log},
	} {
		wg.Add(1)
		go func(w *jobs.Worker) { defer wg.Done(); w.Run(ctx) }(w)
	}
	defer func() { cancel(); wg.Wait() }()

	time.Sleep(500 * time.Millisecond) // let the listeners start
	target := newID()
	if _, err := q.StartPipeline(context.Background(), "selftest", "project", target, 1); err != nil {
		t.Fatal(err)
	}

	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if count(t, pool, target, "selftest_c") == 1 && status(t, pool, target, "selftest_c") == "done" {
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	t.Fatal("pipeline did not finish within 5s (the wake-up signal may not be working)")
}

func TestWorkerFailsJobWithNoHandler(t *testing.T) {
	pool := dbtest.Pool(t)
	if _, err := pool.Exec(context.Background(), `DELETE FROM jobs`); err != nil {
		t.Fatal(err)
	}
	q := jobs.NewQueue(pool)
	target := newID()
	if _, err := q.Enqueue(context.Background(), jobs.EnqueueParams{
		Type: "unknown_stage", Runner: jobs.RunnerGo, TargetType: "project", TargetID: target, MaxTries: 1}); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	w := &jobs.Worker{Queue: q, Pool: pool, Runner: jobs.RunnerGo, ID: "t", Handlers: map[string]jobs.Handler{},
		Concurrency: 1, PollInterval: 200 * time.Millisecond, Log: slog.New(slog.NewTextHandler(io.Discard, nil))}
	done := make(chan struct{})
	go func() { w.Run(ctx); close(done) }()
	defer func() { cancel(); <-done }()

	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if status(t, pool, target, "unknown_stage") == "failed" {
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	t.Fatal("job with no handler was not failed")
}

func TestHandlerPanicBecomesAFailure(t *testing.T) {
	pool := dbtest.Pool(t)
	if _, err := pool.Exec(context.Background(), `DELETE FROM jobs`); err != nil {
		t.Fatal(err)
	}
	q := jobs.NewQueue(pool)
	target := newID()
	if _, err := q.Enqueue(context.Background(), jobs.EnqueueParams{
		Type: "boom", Runner: jobs.RunnerGo, TargetType: "project", TargetID: target, MaxTries: 1}); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	w := &jobs.Worker{Queue: q, Pool: pool, Runner: jobs.RunnerGo, ID: "t",
		Handlers:    map[string]jobs.Handler{"boom": func(context.Context, *jobs.Job) (map[string]any, error) { panic("oops") }},
		Concurrency: 1, PollInterval: 200 * time.Millisecond, Log: slog.New(slog.NewTextHandler(io.Discard, nil))}
	done := make(chan struct{})
	go func() { w.Run(ctx); close(done) }()
	defer func() { cancel(); <-done }()

	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if status(t, pool, target, "boom") == "failed" {
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	t.Fatal("a panicking handler was not turned into a failed job")
}
