package pipeline

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
)

// StageGithubHistory is stage A2 of authorship proof (architecture section 30.4).
const StageGithubHistory = "github_history"

// maxPushPages is how many pages of 100 branch changes we read from GitHub's activity records.
const maxPushPages = 10

// HistoryLimits caps how much history one project reads (settings GITHUB_HISTORY_*). A claim past a limit is listed
// under "skipped_claims" with the limit named, so the card can say "could not trace: repo too large".
type HistoryLimits struct {
	FilesPerClaim    int
	ClaimsPerProject int
	CommitsPerFile   int
	// BranchCommits is how much of the branch we read to tie pushes to commits.
	BranchCommits int
}

// claimMapQueries read the code maps (stage A1) of the subject's claims, oldest claim first.
var claimMapQueries = map[string]string{
	"project": `SELECT m.claim_id::text, m.files, coalesce(m.commit_sha, '') FROM claim_code_maps m
	              JOIN claims c ON c.id = m.claim_id
	             WHERE c.project_id = $1::uuid AND m.not_traced_reason IS NULL ORDER BY c.created_at, c.id`,
	"candidate_project": `SELECT m.claim_id::text, m.files, coalesce(m.commit_sha, '') FROM claim_code_maps m
	              JOIN claims c ON c.id = m.claim_id
	             WHERE c.candidate_project_id = $1::uuid AND m.not_traced_reason IS NULL ORDER BY c.created_at, c.id`,
}

type lineRange struct {
	Path  string `json:"path"`
	Start int    `json:"start"`
	End   int    `json:"end"`
}

type claimMap struct {
	claimID string
	files   []lineRange
	sha     string
}

// GithubHistory is stage A2: for every file the code maps point at, GitHub's blame at the traced commit (cut to the
// mapped lines) and the commits that changed the file, with author account, commit time and, where GitHub recorded
// it, push time. Official API only. Facts only: the shares and flags are worked out in Python (authorship_read).
// No repository, a private one or one GitHub cannot reach ends as "found: false" with the reason, never a mark
// against anyone.
func GithubHistory(pool *pgxpool.Pool, gh *github.Client, limits HistoryLimits) jobs.Handler {
	return func(ctx context.Context, job *jobs.Job) (map[string]any, error) {
		query, ok := repoLinkQueries[job.TargetType]
		if !ok {
			return nil, fmt.Errorf("github_history works on a project or a resume project, not a %q", job.TargetType)
		}
		var link *string
		if err := pool.QueryRow(ctx, query, job.TargetID).Scan(&link); err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				return nil, fmt.Errorf("%s %s does not exist", job.TargetType, job.TargetID)
			}
			return nil, fmt.Errorf("find repository link: %w", err)
		}
		owner, name, reason := repoOrReason(strings.TrimSpace(deref(link)))
		if reason != "" {
			return map[string]any{"found": false, "reason": reason}, nil
		}
		maps, err := loadClaimMaps(ctx, pool, job.TargetType, job.TargetID)
		if err != nil {
			return nil, err
		}
		out, err := readHistory(ctx, gh, limits, owner, name, maps)
		if err != nil {
			if job.MaxTries > 0 && job.Tries >= job.MaxTries {
				// Same as the GitHub data stage: end as "could not trace" so the stages after this one still run.
				return map[string]any{"found": false, "repo": owner + "/" + name,
					"reason": "GitHub could not be reached after several tries", "retry_error": err.Error()}, nil
			}
			return nil, err
		}
		if sha, _ := out["commit_sha"].(string); sha != "" {
			traced, _ := out["traced_claims"].([]string)
			if _, err := pool.Exec(ctx, `UPDATE claim_code_maps SET commit_sha = $1 WHERE claim_id = ANY($2::uuid[])`,
				sha, traced); err != nil {
				return nil, fmt.Errorf("save the traced commit: %w", err)
			}
		}
		delete(out, "traced_claims")
		return out, nil
	}
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

func loadClaimMaps(ctx context.Context, pool *pgxpool.Pool, targetType, targetID string) ([]claimMap, error) {
	rows, err := pool.Query(ctx, claimMapQueries[targetType], targetID)
	if err != nil {
		return nil, fmt.Errorf("read the code maps: %w", err)
	}
	defer rows.Close()
	var out []claimMap
	for rows.Next() {
		var m claimMap
		var raw []byte
		if err := rows.Scan(&m.claimID, &raw, &m.sha); err != nil {
			return nil, fmt.Errorf("read the code maps: %w", err)
		}
		var files []lineRange
		if err := json.Unmarshal(raw, &files); err != nil {
			return nil, fmt.Errorf("read the code map of claim %s: %w", m.claimID, err)
		}
		for _, f := range files {
			f.Path = strings.TrimLeft(strings.TrimPrefix(strings.TrimSpace(f.Path), "./"), "/")
			if f.Path == "" || f.Start < 1 || f.End < f.Start {
				continue
			}
			m.files = append(m.files, f)
		}
		if len(m.files) > 0 {
			out = append(out, m)
		}
	}
	return out, rows.Err()
}

func readHistory(ctx context.Context, gh *github.Client, limits HistoryLimits, owner, name string, maps []claimMap) (map[string]any, error) {
	repo, err := gh.Repo(ctx, owner, name)
	if errors.Is(err, github.ErrNotFound) {
		return map[string]any{"found": false, "repo": owner + "/" + name, "reason": "the repository does not exist or is private"}, nil
	}
	if err != nil {
		return nil, err // a rate limit or a network problem: the queue tries again later
	}
	head, err := gh.Commits(ctx, owner, name, repo.DefaultBranch, time.Time{}, 1)
	if errors.Is(err, github.ErrNotFound) || (err == nil && len(head) == 0) {
		return map[string]any{"found": false, "repo": repo.FullName, "reason": "the repository is empty"}, nil
	}
	if err != nil {
		return nil, err
	}
	// The line ranges belong to the commit code locate read; without one, the head of the default branch.
	sha := head[0].SHA
	for _, m := range maps {
		if m.sha != "" {
			sha = m.sha
			break
		}
	}

	// Which claims we trace, and the mapped lines per file across them.
	traced := []string{}
	skippedClaims := []map[string]any{}
	mapped := map[string][]lineRange{}
	for _, m := range maps {
		files := map[string]bool{}
		for _, f := range m.files {
			files[f.Path] = true
		}
		switch {
		case len(files) > limits.FilesPerClaim:
			skippedClaims = append(skippedClaims, map[string]any{"claim_id": m.claimID,
				"reason": fmt.Sprintf("repo too large: the feature spans more than %d files", limits.FilesPerClaim)})
		case len(traced) >= limits.ClaimsPerProject:
			skippedClaims = append(skippedClaims, map[string]any{"claim_id": m.claimID,
				"reason": fmt.Sprintf("repo too large: more than %d features to trace", limits.ClaimsPerProject)})
		default:
			traced = append(traced, m.claimID)
			for _, f := range m.files {
				mapped[f.Path] = append(mapped[f.Path], f)
			}
		}
	}
	paths := make([]string, 0, len(mapped))
	for p := range mapped {
		paths = append(paths, p)
	}
	sort.Strings(paths)

	files := []map[string]any{}
	shas := map[string]bool{}
	for _, p := range paths {
		entry := map[string]any{"path": p}
		blame, err := gh.Blame(ctx, owner, name, sha, p)
		if errors.Is(err, github.ErrNotFound) {
			entry["blame"], entry["missing"] = []github.BlameRange{}, true
			files = append(files, entry)
			continue
		}
		if err != nil {
			return nil, err
		}
		cut := cutToMapped(blame, mapped[p])
		for _, r := range cut {
			shas[r.SHA] = true
		}
		entry["blame"] = cut
		files = append(files, entry)

		changed, err := gh.FileCommits(ctx, owner, name, sha, p, limits.CommitsPerFile)
		if err != nil && !errors.Is(err, github.ErrNotFound) {
			return nil, err
		}
		for _, c := range changed {
			shas[c.SHA] = true
		}
	}

	pushedAt, haveRecords, err := pushTimes(ctx, gh, owner, name, repo.DefaultBranch, sha, limits.BranchCommits)
	if err != nil {
		return nil, err
	}
	commits := map[string]any{}
	allPushed := true
	for s := range shas {
		c, err := gh.CommitDetail(ctx, owner, name, s)
		if errors.Is(err, github.ErrNotFound) {
			continue
		}
		if err != nil {
			return nil, err
		}
		var login, pushed any
		if c.AuthorLogin != "" {
			login = c.AuthorLogin
		}
		if at, ok := pushedAt[s]; ok {
			pushed = at.UTC().Format(time.RFC3339)
		} else {
			allPushed = false
		}
		commits[s] = map[string]any{
			"author_login": login, "committed_at": c.CommittedAt.UTC().Format(time.RFC3339), "pushed_at": pushed,
			"message": c.Message, "additions": c.Additions, "deletions": c.Deletions, "files_changed": c.FilesChanged,
			"parents": c.Parents, "is_bot": c.IsBot,
		}
	}
	dateSource := "commit"
	if haveRecords && allPushed {
		dateSource = "push"
	}

	count, err := gh.CommitCount(ctx, owner, name, sha)
	if err != nil && !errors.Is(err, github.ErrNotFound) {
		return nil, err
	}
	var parent any
	if repo.Parent != nil {
		parent = repo.Parent.FullName
	}
	return map[string]any{
		"found": true, "repo": repo.FullName, "branch": repo.DefaultBranch, "commit_sha": sha, "date_source": dateSource,
		"files": files, "commits": commits, "repo_commit_count": count, "is_fork": repo.Fork, "parent_repo": parent,
		"skipped_claims": skippedClaims, "traced_claims": traced,
	}, nil
}

// pushTimes ties commits to GitHub's own push records. haveRecords is false when GitHub keeps none for the branch;
// then the dates are commit dates only and the card says so. Only a rate limit is an error (the queue retries).
func pushTimes(ctx context.Context, gh *github.Client, owner, name, branch, sha string, branchCommits int) (map[string]time.Time, bool, error) {
	pushes, err := gh.Pushes(ctx, owner, name, branch, maxPushPages)
	if errors.Is(err, github.ErrRateLimited) {
		return nil, false, err
	}
	if err != nil || len(pushes) == 0 {
		return map[string]time.Time{}, false, nil
	}
	graph, _, err := gh.BranchGraph(ctx, owner, name, sha, branchCommits)
	if errors.Is(err, github.ErrRateLimited) {
		return nil, false, err
	}
	if err != nil {
		return map[string]time.Time{}, false, nil
	}
	return github.PushTimes(pushes, graph), true, nil
}

// cutToMapped keeps only the parts of blame ranges that fall inside the mapped lines of the file.
func cutToMapped(blame []github.BlameRange, mapped []lineRange) []github.BlameRange {
	spans := mergeSpans(mapped)
	out := []github.BlameRange{}
	for _, b := range blame {
		for _, s := range spans {
			start, end := max(b.Start, s.Start), min(b.End, s.End)
			if start <= end {
				out = append(out, github.BlameRange{Start: start, End: end, SHA: b.SHA})
			}
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Start < out[j].Start })
	return out
}

// mergeSpans joins overlapping or touching line ranges, so a line mapped by two claims is counted once.
func mergeSpans(in []lineRange) []lineRange {
	spans := append([]lineRange(nil), in...)
	sort.Slice(spans, func(i, j int) bool { return spans[i].Start < spans[j].Start })
	var out []lineRange
	for _, s := range spans {
		if n := len(out); n > 0 && s.Start <= out[n-1].End+1 {
			out[n-1].End = max(out[n-1].End, s.End)
			continue
		}
		out = append(out, s)
	}
	return out
}
