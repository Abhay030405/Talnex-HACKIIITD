package pipeline

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/candidates"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
)

// StageAutoConfirm runs after resume_read in recruiter_candidate (migration 000030).
const StageAutoConfirm = "auto_confirm"

// Starter starts a pipeline for a target; jobs.Queue does this.
type Starter interface {
	StartPipeline(ctx context.Context, pipeline, targetType, targetID string, run int) ([]string, error)
}

// StartChecks confirms the candidate's projects and coding profiles and starts every check: the coding profiles once,
// and one Recruiter pipeline per project. The confirm page and the auto_confirm stage both use it, so they cannot drift.
// Safe to call twice: starting a pipeline again adds no second set of jobs.
func StartChecks(ctx context.Context, store *candidates.Store, q Starter, candidateID string, in candidates.Confirmation) (int, []string, error) {
	projectIDs, err := store.Confirm(ctx, candidateID, in)
	if err != nil {
		return 0, nil, err
	}
	run, err := store.ReadRun(ctx, candidateID)
	if err != nil {
		return 0, nil, fmt.Errorf("find run: %w", err)
	}
	coding, err := store.CheckChosen(ctx, candidateID, "coding_profiles")
	if err != nil {
		return 0, nil, err
	}
	if coding {
		if _, err := q.StartPipeline(ctx, RecruiterCoding, "candidate", candidateID, run); err != nil {
			return 0, nil, fmt.Errorf("start coding checks: %w", err)
		}
	}
	for _, projectID := range projectIDs {
		if _, err := q.StartPipeline(ctx, Recruiter, "candidate_project", projectID, run); err != nil {
			return 0, nil, fmt.Errorf("start project check: %w", err)
		}
	}
	if err := store.MarkStarted(ctx, candidateID); err != nil {
		return 0, nil, fmt.Errorf("mark started: %w", err)
	}
	return run, projectIDs, nil
}

// AsFound is the confirmation the recruiter would send by pressing confirm without changing anything.
func AsFound(f candidates.Found) candidates.Confirmation {
	profiles := map[string]string{}
	for site, handle := range f.CodingHandles {
		if link := f.CodingLinks[site]; link != "" {
			profiles[site] = link
		} else if handle != "" {
			profiles[site] = handle
		}
	}
	return candidates.Confirmation{Projects: f.Projects, CodingProfiles: profiles}
}

// AutoConfirm starts the checks on what the resume reader found, for a candidate whose role has auto_confirm on.
// Anything else is left for the recruiter's confirm page: no role, auto_confirm off, a resume that was not read, or
// what was found does not pass the confirm page's own checks (for example no projects at all).
func AutoConfirm(pool *pgxpool.Pool) jobs.Handler {
	store := candidates.NewStore(pool)
	queue := jobs.NewQueue(pool)
	return func(ctx context.Context, job *jobs.Job) (map[string]any, error) {
		if job.TargetType != "candidate" {
			return nil, fmt.Errorf("auto_confirm works on a candidate, not a %q", job.TargetType)
		}
		auto, err := store.AutoConfirmRole(ctx, job.TargetID)
		if err != nil {
			return nil, err
		}
		if !auto {
			return map[string]any{"skipped": true, "reason": "waits for the recruiter to confirm"}, nil
		}
		found, err := store.Found(ctx, job.TargetID)
		if err != nil {
			return nil, err
		}
		if found.Status != "awaiting_confirmation" {
			return map[string]any{"skipped": true, "reason": "the resume is " + found.Status}, nil
		}
		run, projects, err := StartChecks(ctx, store, queue, job.TargetID, AsFound(found))
		var bad candidates.ErrBadInput
		if errors.As(err, &bad) {
			return map[string]any{"skipped": true, "reason": "left for the recruiter to confirm: " + bad.Error()}, nil
		}
		if err != nil {
			return nil, err
		}
		return map[string]any{"started": true, "run": run, "projects": len(projects)}, nil
	}
}
