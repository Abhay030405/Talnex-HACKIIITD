package pipeline_test

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
)

type fakeStore struct {
	prefixes []string
	fail     bool
}

func (f *fakeStore) DeletePrefix(_ context.Context, prefix string) error {
	if f.fail {
		return errors.New("storage down")
	}
	f.prefixes = append(f.prefixes, prefix)
	return nil
}

// cleanupCandidate makes a candidate with a resume file and one project with bullets.
func cleanupCandidate(t *testing.T, pool *pgxpool.Pool, withReport, gaps bool) string {
	t.Helper()
	ctx := context.Background()
	var owner, cand string
	if err := pool.QueryRow(ctx, `INSERT INTO users (email) VALUES ($1) RETURNING id::text`, uuid.NewString()+"@example.com").Scan(&owner); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `INSERT INTO candidates (owner_id, label, resume_key, status, status_detail)
		VALUES ($1::uuid, 'c', 'resumes/x/resume.pdf', 'reporting', 'building') RETURNING id::text`, owner).Scan(&cand); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `UPDATE candidates SET resume_key = 'resumes/' || id::text || '/resume.pdf' WHERE id = $1::uuid`, cand); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO candidate_projects (candidate_id, name, bullets) VALUES ($1::uuid, 'P', ARRAY['built a thing','used Go'])`, cand); err != nil {
		t.Fatal(err)
	}
	if withReport {
		if _, err := pool.Exec(ctx, `INSERT INTO candidate_reports (candidate_id, report, has_gaps) VALUES ($1::uuid, '{}', $2)`, cand, gaps); err != nil {
			t.Fatal(err)
		}
	}
	return cand
}

type candState struct {
	resumeKey      *string
	deletedAt      *string
	status         string
	detail         *string
	bullets        []string
	reportSurvived bool
}

func readCand(t *testing.T, pool *pgxpool.Pool, id string) candState {
	t.Helper()
	var s candState
	if err := pool.QueryRow(context.Background(),
		`SELECT resume_key, resume_deleted_at::text, status, status_detail FROM candidates WHERE id = $1::uuid`, id).
		Scan(&s.resumeKey, &s.deletedAt, &s.status, &s.detail); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(context.Background(),
		`SELECT bullets FROM candidate_projects WHERE candidate_id = $1::uuid`, id).Scan(&s.bullets); err != nil {
		t.Fatal(err)
	}
	_ = pool.QueryRow(context.Background(),
		`SELECT EXISTS (SELECT 1 FROM candidate_reports WHERE candidate_id = $1::uuid)`, id).Scan(&s.reportSurvived)
	return s
}

func TestResumeCleanupDeletesTheResumeAndKeepsTheResults(t *testing.T) {
	for name, gaps := range map[string]bool{"no gaps": false, "with gaps": true} {
		t.Run(name, func(t *testing.T) {
			pool := dbtest.Pool(t)
			cand := cleanupCandidate(t, pool, true, gaps)
			other := cleanupCandidate(t, pool, true, false)
			store := &fakeStore{}
			h := pipeline.ResumeCleanup(pool, store)
			job := &jobs.Job{TargetType: "candidate", TargetID: cand}

			want := "done"
			if gaps {
				want = "done_with_gaps"
			}
			// Twice: the second run must change nothing.
			var firstDeletedAt *string
			for i := 0; i < 2; i++ {
				if _, err := h(context.Background(), job); err != nil {
					t.Fatalf("run %d: %v", i+1, err)
				}
				s := readCand(t, pool, cand)
				if s.resumeKey != nil || s.deletedAt == nil || s.status != want || s.detail != nil || len(s.bullets) != 0 || !s.reportSurvived {
					t.Fatalf("run %d: %+v", i+1, s)
				}
				if i == 0 {
					firstDeletedAt = s.deletedAt
				} else if *s.deletedAt != *firstDeletedAt {
					t.Errorf("deleted-at moved on the second run: %s -> %s", *firstDeletedAt, *s.deletedAt)
				}
			}
			if len(store.prefixes) != 2 || store.prefixes[0] != "resumes/"+cand+"/" {
				t.Errorf("deleted prefixes = %v", store.prefixes)
			}

			o := readCand(t, pool, other)
			if o.resumeKey == nil || o.status != "reporting" || len(o.bullets) != 2 || o.deletedAt != nil {
				t.Errorf("another candidate was touched: %+v", o)
			}
		})
	}
}

func TestResumeCleanupWaitsForTheReport(t *testing.T) {
	pool := dbtest.Pool(t)
	cand := cleanupCandidate(t, pool, false, false)
	store := &fakeStore{}
	_, err := pipeline.ResumeCleanup(pool, store)(context.Background(), &jobs.Job{TargetType: "candidate", TargetID: cand})
	if err == nil {
		t.Fatal("cleanup ran without a report")
	}
	s := readCand(t, pool, cand)
	if s.resumeKey == nil || s.status != "reporting" || len(s.bullets) != 2 || len(store.prefixes) != 0 {
		t.Errorf("the resume was touched without a report: %+v, deleted %v", s, store.prefixes)
	}
}

func TestResumeCleanupKeepsDatabaseStateWhenStorageFails(t *testing.T) {
	pool := dbtest.Pool(t)
	cand := cleanupCandidate(t, pool, true, false)
	if _, err := pipeline.ResumeCleanup(pool, &fakeStore{fail: true})(context.Background(), &jobs.Job{TargetType: "candidate", TargetID: cand}); err == nil {
		t.Fatal("expected an error so the queue tries again")
	}
	if s := readCand(t, pool, cand); s.resumeKey == nil || len(s.bullets) != 2 || s.status != "reporting" {
		t.Errorf("state changed although the files were not deleted: %+v", s)
	}
}

func TestResumeCleanupRefusesOtherTargets(t *testing.T) {
	pool := dbtest.Pool(t)
	if _, err := pipeline.ResumeCleanup(pool, &fakeStore{})(context.Background(), &jobs.Job{TargetType: "project", TargetID: uuid.NewString()}); err == nil {
		t.Error("a project target should be refused")
	}
}
