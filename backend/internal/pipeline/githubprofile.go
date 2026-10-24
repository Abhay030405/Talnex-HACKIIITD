package pipeline

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
)

// StageGithubProfile reads the candidate's whole public GitHub account, beyond the projects on the resume.
const StageGithubProfile = "github_profile"

// githubProfileSignal is the name of the one row this stage keeps per candidate in coding_signals.
const githubProfileSignal = "github_profile"

const (
	profileMaxRepos    = 100 // repos listed (one API page)
	profileSampleRepos = 20  // original repos, most recently pushed, whose last year of commits is read
	profileCommitPage  = 100 // commits read per sampled repo (one API page)
	oneDayMinCommits   = 5   // a repo needs this many commits before "most of them on one day" means anything
	oneDayShare        = 0.8
)

// MonthCount is the number of commits in one calendar month ("2006-01").
type MonthCount struct {
	Month   string `json:"month"`
	Commits int    `json:"commits"`
}

// RepoPattern is how the commits of one sampled repo are spread over time.
type RepoPattern struct {
	Repo            string  `json:"repo"`
	Commits         int     `json:"commits"`
	ActiveDays      int     `json:"active_days"`
	BusiestDayShare float64 `json:"busiest_day_share"`
	MostOnOneDay    bool    `json:"most_on_one_day"`
	PageFull        bool    `json:"page_full"` // the sample hit its page size, so the repo has at least this many
}

// GithubProfileFacts is what the stage keeps as evidence. Facts only: none of it is a verdict.
type GithubProfileFacts struct {
	Account            string         `json:"account"`
	AccountFrom        string         `json:"account_from"`
	CreatedAt          time.Time      `json:"created_at"`
	AccountAgeDays     int            `json:"account_age_days"`
	PublicRepos        int            `json:"public_repos"`
	Followers          int            `json:"followers"`
	Originals          int            `json:"originals"`
	Forks              int            `json:"forks"`
	Languages          map[string]int `json:"languages"` // main language -> number of original repos
	Since              time.Time      `json:"since"`
	ReposSampled       int            `json:"repos_sampled"`
	CommitsSampled     int            `json:"commits_sampled"`
	Months             []MonthCount   `json:"months"` // the last 12 months, oldest first
	ActiveMonths       int            `json:"active_months"`
	LongestQuietMonths int            `json:"longest_quiet_months"`
	OneDayRepos        int            `json:"one_day_repos"`
	Stars              int            `json:"stars"`        // stars on all original repos together
	MostStarred        string         `json:"most_starred"` // the original repo with the most stars
	MostStarredStars   int            `json:"most_starred_stars"`
	LastPush           time.Time      `json:"last_push"`              // the newest push to any original repo
	ExternalPRs        *int           `json:"external_prs,omitempty"` // pull requests on others' repos; nil if not read
	Repos              []RepoPattern  `json:"repos"`
}

// SummarizeGithubProfile turns an account, its repos and the sampled commits into facts. Pure, so it is easy to test.
func SummarizeGithubProfile(u github.User, repos []github.Repo, commits map[string][]github.Commit, now time.Time) GithubProfileFacts {
	start := time.Date(now.Year(), now.Month(), 1, 0, 0, 0, 0, time.UTC).AddDate(0, -11, 0)
	f := GithubProfileFacts{
		Account: u.Login, AccountFrom: "the owner of the repositories on the resume", CreatedAt: u.CreatedAt,
		AccountAgeDays: int(now.Sub(u.CreatedAt).Hours() / 24), PublicRepos: u.PublicRepos, Followers: u.Followers,
		Languages: map[string]int{}, Since: start, Repos: []RepoPattern{},
	}
	perMonth := map[string]int{}
	for _, r := range repos {
		if r.Fork {
			f.Forks++
			continue
		}
		f.Originals++
		f.Stars += r.Stars
		if r.Stars > f.MostStarredStars {
			f.MostStarred, f.MostStarredStars = r.FullName, r.Stars
		}
		if r.PushedAt.After(f.LastPush) {
			f.LastPush = r.PushedAt
		}
		if r.Language != "" {
			f.Languages[r.Language]++
		}
		cs, sampled := commits[r.FullName]
		if !sampled {
			continue
		}
		f.ReposSampled++
		days := map[string]int{}
		busiest := 0
		for _, c := range cs {
			perMonth[c.Date.UTC().Format("2006-01")]++
			d := c.Date.UTC().Format("2006-01-02")
			days[d]++
			busiest = max(busiest, days[d])
		}
		p := RepoPattern{Repo: r.FullName, Commits: len(cs), ActiveDays: len(days), PageFull: len(cs) >= profileCommitPage}
		if len(cs) > 0 {
			p.BusiestDayShare = float64(busiest) / float64(len(cs))
		}
		p.MostOnOneDay = len(cs) >= oneDayMinCommits && p.BusiestDayShare >= oneDayShare
		if p.MostOnOneDay {
			f.OneDayRepos++
		}
		f.CommitsSampled += len(cs)
		f.Repos = append(f.Repos, p)
	}
	quiet := 0
	for i := 0; i < 12; i++ {
		m := start.AddDate(0, i, 0).Format("2006-01")
		f.Months = append(f.Months, MonthCount{Month: m, Commits: perMonth[m]})
		if perMonth[m] > 0 {
			f.ActiveMonths++
			quiet = 0
		} else {
			quiet++
			f.LongestQuietMonths = max(f.LongestQuietMonths, quiet)
		}
	}
	return f
}

// GithubProfile is the GitHub part of the "coding profiles" stage. It looks past the resume at the whole public account
// that owns the resume's repos: how old it is, original repos vs forks, main languages, and over the last year how
// steady the commits are and whether a repo's commits mostly landed on one day. The facts are kept as one row in
// coding_signals with weight "not_suspicious": evidence beside the score, never a verdict. A quiet account is not a
// mark against anyone, since much work happens in private repos. Running it twice replaces the row.
func GithubProfile(pool *pgxpool.Pool, gh *github.Client, now func() time.Time) jobs.Handler {
	return func(ctx context.Context, job *jobs.Job) (map[string]any, error) {
		if job.TargetType != "candidate" {
			return nil, fmt.Errorf("github_profile works on a candidate, not a %q", job.TargetType)
		}
		account, err := resumeAccount(ctx, pool, job.TargetID)
		if err != nil {
			return nil, err
		}
		if account == "" {
			return map[string]any{"skipped": true, "reason": "no GitHub repository on the resume, so no account to read"}, nil
		}
		u, err := gh.User(ctx, account)
		if errors.Is(err, github.ErrNotFound) {
			return map[string]any{"found": false, "account": account, "reason": "GitHub has no public account with this name"}, nil
		}
		if err != nil {
			return nil, err // a rate limit or a network problem: the queue tries again later
		}
		repos, err := gh.OwnedRepos(ctx, u.Login, profileMaxRepos)
		if err != nil {
			return nil, err
		}
		t := now()
		since := time.Date(t.Year(), t.Month(), 1, 0, 0, 0, 0, time.UTC).AddDate(0, -11, 0)
		commits := map[string][]github.Commit{}
		for _, r := range repos {
			if len(commits) >= profileSampleRepos {
				break
			}
			if r.Fork || r.PushedAt.Before(since) {
				continue
			}
			owner, name, _ := strings.Cut(r.FullName, "/")
			cs, err := gh.AuthorCommits(ctx, owner, name, u.Login, since, profileCommitPage)
			if errors.Is(err, github.ErrNotFound) {
				continue // an empty repo has no commits yet
			}
			if err != nil {
				return nil, err
			}
			commits[r.FullName] = cs
		}
		facts := SummarizeGithubProfile(u, repos, commits, t)
		if n, err := gh.ExternalPRs(ctx, account); err == nil { // a hint only: a failed search just leaves it out
			facts.ExternalPRs = &n
		}
		if err := saveGithubProfile(ctx, pool, job.TargetID, facts); err != nil {
			return nil, err
		}
		return map[string]any{
			"found": true, "account": facts.Account, "originals": facts.Originals, "forks": facts.Forks,
			"repos_sampled": facts.ReposSampled, "active_months": facts.ActiveMonths, "one_day_repos": facts.OneDayRepos,
		}, nil
	}
}

// resumeAccount is the GitHub account that owns most of the resume's repos ("" when no project links to GitHub).
func resumeAccount(ctx context.Context, pool *pgxpool.Pool, candidateID string) (string, error) {
	rows, err := pool.Query(ctx, `SELECT coalesce(repo_url, '') FROM candidate_projects WHERE candidate_id = $1::uuid ORDER BY created_at`, candidateID)
	if err != nil {
		return "", fmt.Errorf("read resume repos: %w", err)
	}
	defer rows.Close()
	count, first := map[string]int{}, map[string]string{}
	best := ""
	for rows.Next() {
		var link string
		if err := rows.Scan(&link); err != nil {
			return "", err
		}
		owner, _, ok := github.ParseRepoURL(link)
		if !ok {
			continue
		}
		key := strings.ToLower(owner) // GitHub names ignore case
		if _, seen := first[key]; !seen {
			first[key] = owner
		}
		count[key]++
		if best == "" || count[key] > count[strings.ToLower(best)] {
			best = first[key]
		}
	}
	return best, rows.Err()
}

// saveGithubProfile replaces the candidate's GitHub profile row in one step, so a second run leaves exactly one row.
func saveGithubProfile(ctx context.Context, pool *pgxpool.Pool, candidateID string, f GithubProfileFacts) error {
	evidence, err := json.Marshal(f)
	if err != nil {
		return err
	}
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck
	if _, err := tx.Exec(ctx, `DELETE FROM coding_signals WHERE candidate_id = $1::uuid AND site = 'github' AND signal = $2`,
		candidateID, githubProfileSignal); err != nil {
		return fmt.Errorf("clear old GitHub profile: %w", err)
	}
	if _, err := tx.Exec(ctx, `INSERT INTO coding_signals (candidate_id, site, signal, weight, evidence)
		VALUES ($1::uuid, 'github', $2, 'not_suspicious', $3::jsonb)`, candidateID, githubProfileSignal, string(evidence)); err != nil {
		return fmt.Errorf("save GitHub profile: %w", err)
	}
	return tx.Commit(ctx)
}
