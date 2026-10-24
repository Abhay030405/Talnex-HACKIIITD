package pipeline

import (
	"context"
	"errors"
	"fmt"
	"path"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
)

// Files that say what a project is built with, and files that say how it runs.
var dependencyFiles = map[string]bool{
	"package.json": true, "package-lock.json": true, "yarn.lock": true, "pnpm-lock.yaml": true,
	"requirements.txt": true, "pyproject.toml": true, "pipfile": true, "poetry.lock": true,
	"go.mod": true, "cargo.toml": true, "pom.xml": true, "build.gradle": true, "build.gradle.kts": true,
	"gemfile": true, "composer.json": true, "pubspec.yaml": true,
}

var runFiles = map[string]bool{
	"dockerfile": true, "docker-compose.yml": true, "docker-compose.yaml": true, "compose.yml": true, "compose.yaml": true,
	"makefile": true, "procfile": true, "vercel.json": true, "netlify.toml": true,
}

const maxListedFiles = 300

// repoLinkQueries find the repository link of whatever the job is about.
var repoLinkQueries = map[string]string{
	"project":           `SELECT repo_url FROM projects WHERE id = $1::uuid`,
	"candidate_project": `SELECT repo_url FROM candidate_projects WHERE id = $1::uuid`,
}

// GithubCheck is the "GitHub data" stage (architecture sections 7, 8 and 28). It reads facts from GitHub's
// official API and saves them in the job result for the checks that come after it: repo dates, languages, the file
// list, dependency and run files. It reads no file contents and is the same for a hackathon project and a project on
// a resume. A repository that is missing, private or not on GitHub ends as "found: false" with the reason; that is
// never a mark against anyone.
func GithubCheck(pool *pgxpool.Pool, gh *github.Client) jobs.Handler {
	return func(ctx context.Context, job *jobs.Job) (map[string]any, error) {
		query, ok := repoLinkQueries[job.TargetType]
		if !ok {
			return nil, fmt.Errorf("github_check works on a project or a resume project, not a %q", job.TargetType)
		}
		var link *string
		if err := pool.QueryRow(ctx, query, job.TargetID).Scan(&link); err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				return nil, fmt.Errorf("%s %s does not exist", job.TargetType, job.TargetID)
			}
			return nil, fmt.Errorf("find repository link: %w", err)
		}
		if link == nil || strings.TrimSpace(*link) == "" {
			return map[string]any{"found": false, "reason": "no repository link was given"}, nil
		}
		owner, name, ok := github.ParseRepoURL(*link)
		if !ok {
			return map[string]any{"found": false, "url": *link, "reason": "the link is not a GitHub repository"}, nil
		}
		out, err := readRepo(ctx, gh, owner, name)
		if err != nil && job.MaxTries > 0 && job.Tries >= job.MaxTries {
			// The last try failed (GitHub busy or unreachable). End as "could not check" so the stages after this one
			// still run; a failed stage would leave the whole project stuck. Never a mark against anyone.
			return map[string]any{"found": false, "repo": owner + "/" + name,
				"reason": "GitHub could not be reached after several tries", "retry_error": err.Error()}, nil
		}
		return out, err
	}
}

func readRepo(ctx context.Context, gh *github.Client, owner, name string) (map[string]any, error) {
	repo, err := gh.Repo(ctx, owner, name)
	if errors.Is(err, github.ErrNotFound) {
		return map[string]any{"found": false, "repo": owner + "/" + name, "reason": "the repository does not exist or is private"}, nil
	}
	if err != nil {
		return nil, err // a rate limit or a network problem: the queue tries again later
	}
	out := map[string]any{
		"found": true, "repo": repo.FullName, "private": repo.Private, "fork": repo.Fork, "archived": repo.Archived,
		"created_at": repo.CreatedAt, "pushed_at": repo.PushedAt, "default_branch": repo.DefaultBranch,
		"stars": repo.Stars, "size_kb": repo.SizeKB,
	}
	if repo.Parent != nil {
		out["forked_from"] = repo.Parent.FullName
	}

	languages, err := gh.Languages(ctx, owner, name)
	if err != nil && !errors.Is(err, github.ErrNotFound) {
		return nil, err
	}
	out["languages"] = languages

	tree, err := gh.Files(ctx, owner, name, repo.DefaultBranch)
	if errors.Is(err, github.ErrNotFound) { // an empty repository
		out["files"], out["file_count"], out["empty"] = []string{}, 0, true
		return out, nil
	}
	if err != nil {
		return nil, err
	}
	summarise(out, tree)
	return out, nil
}

// summarise adds the file facts. Only file names are kept, never contents.
func summarise(out map[string]any, tree github.Tree) {
	var files, deps, runs []string
	readme := false
	for _, e := range tree.Entries {
		if e.Type != "blob" {
			continue
		}
		files = append(files, e.Path)
		base := strings.ToLower(path.Base(e.Path))
		switch {
		case dependencyFiles[base]:
			deps = append(deps, e.Path)
		case runFiles[base]:
			runs = append(runs, e.Path)
		}
		if strings.HasPrefix(base, "readme") && !strings.Contains(e.Path, "/") {
			readme = true
		}
	}
	sort.Strings(files)
	shown := files
	if len(shown) > maxListedFiles {
		shown = shown[:maxListedFiles]
	}
	out["file_count"] = len(files)
	out["files"] = shown
	out["files_truncated"] = len(files) > maxListedFiles || tree.Truncated
	out["dependency_files"] = nonNil(deps)
	out["run_files"] = nonNil(runs)
	out["has_readme"] = readme
}

func nonNil(s []string) []string {
	if s == nil {
		return []string{}
	}
	return s
}
