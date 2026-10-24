package pipeline

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/checks/eventdates"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/checks/sponsorfiles"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
)

// The two hackathon-only Go stages that use the event's own dates and sponsor tools. Both only read facts from
// GitHub's official API and save them in the job result; the red flags are decided later, in Python (`repo_checks`).
const (
	StageEventDates   = "event_dates"
	StageSponsorFiles = "sponsor_files"
)

const (
	commitsRead         = 100 // how many commits we read to judge the history
	maxDependencyFiles  = 8
	skipNotAProjectText = "this check is for hackathon projects"
)

func skipped(reason string) map[string]any { return map[string]any{"skipped": true, "reason": reason} }

type projectRepo struct {
	link     string
	startsAt time.Time
	endsAt   time.Time
	sponsors []string
}

func loadProjectRepo(ctx context.Context, pool *pgxpool.Pool, projectID string) (projectRepo, error) {
	var p projectRepo
	var link *string
	err := pool.QueryRow(ctx, `
		SELECT p.repo_url, e.starts_at, e.ends_at, e.sponsor_tools
		  FROM projects p JOIN events e ON e.id = p.event_id WHERE p.id = $1::uuid`, projectID).
		Scan(&link, &p.startsAt, &p.endsAt, &p.sponsors)
	if errors.Is(err, pgx.ErrNoRows) {
		return p, fmt.Errorf("project %s does not exist", projectID)
	}
	if err != nil {
		return p, fmt.Errorf("find the project's repository: %w", err)
	}
	if link != nil {
		p.link = strings.TrimSpace(*link)
	}
	return p, nil
}

// repoOrReason returns the owner and name, or the plain-words reason there is nothing to read.
func repoOrReason(link string) (owner, name, reason string) {
	if link == "" {
		return "", "", "no repository link was given"
	}
	owner, name, ok := github.ParseRepoURL(link)
	if !ok {
		return "", "", "the link is not a GitHub repository"
	}
	return owner, name, ""
}

// EventDates is the "code before the event" stage (architecture section 12). It says how much of the final code was
// already there when the event began, when GitHub says the repository was created, and whether the whole history
// looks like one big upload near the deadline. Facts only: a team that built a template first is not accused here.
func EventDates(pool *pgxpool.Pool, gh *github.Client) jobs.Handler {
	return func(ctx context.Context, job *jobs.Job) (map[string]any, error) {
		if job.TargetType != "project" {
			return skipped(skipNotAProjectText), nil
		}
		p, err := loadProjectRepo(ctx, pool, job.TargetID)
		if err != nil {
			return nil, err
		}
		owner, name, reason := repoOrReason(p.link)
		if reason != "" {
			return map[string]any{"found": false, "reason": reason}, nil
		}
		repo, err := gh.Repo(ctx, owner, name)
		if errors.Is(err, github.ErrNotFound) {
			return map[string]any{"found": false, "repo": owner + "/" + name, "reason": "the repository does not exist or is private"}, nil
		}
		if err != nil {
			return nil, err // a rate limit or a network problem: the queue tries again later
		}
		out := map[string]any{
			"found": true, "repo": repo.FullName,
			"starts_at": p.startsAt, "ends_at": p.endsAt, "repo_created_at": repo.CreatedAt,
			"repo_created_before_start": repo.CreatedAt.Before(p.startsAt),
			"fork":                      repo.Fork,
		}

		final, err := gh.TreeAt(ctx, owner, name, repo.DefaultBranch)
		if errors.Is(err, github.ErrNotFound) { // an empty repository
			out["empty"] = true
			return out, nil
		}
		if err != nil {
			return nil, err
		}
		history, err := gh.Commits(ctx, owner, name, repo.DefaultBranch, time.Time{}, commitsRead)
		if err != nil && !errors.Is(err, github.ErrNotFound) {
			return nil, err
		}
		out["commits_read"] = len(history)
		out["commits_all_read"] = len(history) < commitsRead
		out["one_big_upload"] = eventdates.OneBigUpload(history, len(history) < commitsRead, p.endsAt)

		var before github.SnapshotTree
		last, err := gh.Commits(ctx, owner, name, repo.DefaultBranch, p.startsAt, 1)
		if err != nil && !errors.Is(err, github.ErrNotFound) {
			return nil, err
		}
		out["commits_before_start"] = len(last) > 0
		if len(last) > 0 {
			if before, err = gh.TreeAt(ctx, owner, name, last[0].SHA); err != nil && !errors.Is(err, github.ErrNotFound) {
				return nil, err
			}
			out["last_commit_before_start"] = last[0].Date
		}
		res := eventdates.Compare(final.Nodes, before.Nodes)
		out["share_before_start_pct"] = res.SharePct
		out["code_bytes"] = res.TotalBytes
		out["code_bytes_before_start"] = res.BeforeBytes
		out["files"] = res.FilesTotal
		out["files_before_start"] = res.FilesBefore
		out["tree_truncated"] = final.Truncated || before.Truncated
		return out, nil
	}
}

// SponsorFiles is the "sponsor tech listed" half of the sponsor check: for each sponsor tool of the event, is there a
// matching dependency in the project's dependency files? Whether the tool is really called in a real feature is
// checked in Python from the code.
func SponsorFiles(pool *pgxpool.Pool, gh *github.Client) jobs.Handler {
	return func(ctx context.Context, job *jobs.Job) (map[string]any, error) {
		if job.TargetType != "project" {
			return skipped(skipNotAProjectText), nil
		}
		p, err := loadProjectRepo(ctx, pool, job.TargetID)
		if err != nil {
			return nil, err
		}
		if len(p.sponsors) == 0 {
			return skipped("the event lists no sponsor tools"), nil
		}
		owner, name, reason := repoOrReason(p.link)
		if reason != "" {
			return map[string]any{"found": false, "reason": reason, "tools": toolList(p.sponsors, nil)}, nil
		}
		data, err := githubData(ctx, pool, job)
		if err != nil {
			return nil, err
		}
		if data == nil {
			return map[string]any{"found": false, "reason": "no repository data was found (the GitHub data stage found nothing)",
				"tools": toolList(p.sponsors, nil)}, nil
		}
		files := map[string]string{}
		for _, path := range data.dependencyFiles {
			if len(files) == maxDependencyFiles {
				break
			}
			text, err := gh.File(ctx, owner, name, path, data.branch)
			if errors.Is(err, github.ErrNotFound) {
				continue
			}
			if err != nil {
				return nil, err
			}
			files[path] = text
		}
		return map[string]any{"found": true, "repo": owner + "/" + name, "files_read": len(files), "tools": toolList(p.sponsors, files)}, nil
	}
}

func toolList(tools []string, files map[string]string) []map[string]any {
	out := make([]map[string]any, 0, len(tools))
	for _, tool := range tools {
		matches := sponsorfiles.Find(tool, files)
		if matches == nil {
			matches = []sponsorfiles.Match{}
		}
		out = append(out, map[string]any{"tool": tool, "listed": len(matches) > 0, "matches": matches})
	}
	return out
}

type repoData struct {
	branch          string
	dependencyFiles []string
}

// githubData reads what the GitHub data stage saved for this run (the default branch and the dependency files).
func githubData(ctx context.Context, pool *pgxpool.Pool, job *jobs.Job) (*repoData, error) {
	var found *bool
	var branch *string
	var deps []string
	err := pool.QueryRow(ctx, `
		SELECT (result->>'found')::boolean, result->>'default_branch',
		       coalesce(ARRAY(SELECT jsonb_array_elements_text(result->'dependency_files')), '{}')
		  FROM jobs
		 WHERE pipeline IS NOT DISTINCT FROM $1 AND target_type = $2 AND target_id = $3::uuid
		   AND run_number = $4 AND job_type = $5 AND status = 'done'
		 ORDER BY updated_at DESC LIMIT 1`,
		job.Pipeline, job.TargetType, job.TargetID, job.RunNumber, StageGithubCheck).Scan(&found, &branch, &deps)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read the GitHub data result: %w", err)
	}
	if found == nil || !*found || branch == nil {
		return nil, nil
	}
	return &repoData{branch: *branch, dependencyFiles: deps}, nil
}
