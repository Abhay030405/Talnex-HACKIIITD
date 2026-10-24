// Package projects creates and reads hackathon submissions.
package projects

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("project not found")

type Project struct {
	ID           string `json:"id"`
	EventID      string `json:"event_id"`
	TeamName     string `json:"team_name"`
	VideoURL     string `json:"video_url"`
	LiveURL      string `json:"live_url"`
	RepoURL      string `json:"repo_url"`
	TestLoginRef string `json:"test_login_ref"`
	// The team's GitHub accounts from the form (optional), for "who built what" (architecture section 30.6).
	TeamGithubHandles []string  `json:"team_github_handles"`
	Status            string    `json:"status"`
	StatusDetail      string    `json:"status_detail"`
	CreatedAt         time.Time `json:"created_at"`
	UpdatedAt         time.Time `json:"updated_at"`
}

type NewProject struct {
	TeamName string `json:"team_name"`
	VideoURL string `json:"video_url"`
	LiveURL  string `json:"live_url"`
	RepoURL  string `json:"repo_url"`
	// A reference to the test login kept in TinyFish Vault. Never the login itself.
	TestLoginRef string `json:"test_login_ref"`
	// Optional GitHub accounts of the team. Stored trimmed, lowercase and without a leading @.
	TeamGithubHandles []string `json:"team_github_handles"`
	// Abstract is the team's own short description of what they built; it reaches the test prompts as data.
	Abstract string `json:"abstract"`
}

// maxTeamHandles is the most GitHub accounts one team can list.
const maxTeamHandles = 10

// githubLogin is GitHub's rule for account names: letters, digits and single hyphens, not at the start or end.
var githubLogin = regexp.MustCompile(`^[a-z0-9](?:[a-z0-9]|-[a-z0-9]){0,38}$`)

// Validate returns a plain-words problem with the input, or nil.
// A missing link is allowed (the precheck records it as "required item missing"), but a team
// that gives no link at all leaves nothing to check.
func (n *NewProject) Validate() error {
	n.TeamName = strings.TrimSpace(n.TeamName)
	if n.TeamName == "" {
		return errors.New("team_name is required")
	}
	n.TestLoginRef = strings.TrimSpace(n.TestLoginRef)
	for _, f := range []struct {
		label string
		value *string
	}{{"video_url", &n.VideoURL}, {"live_url", &n.LiveURL}, {"repo_url", &n.RepoURL}} {
		*f.value = strings.TrimSpace(*f.value)
		if err := checkURL(f.label, *f.value); err != nil {
			return err
		}
	}
	if n.VideoURL == "" && n.LiveURL == "" && n.RepoURL == "" {
		return errors.New("give at least one of video_url, live_url or repo_url")
	}
	return n.cleanHandles()
}

func (n *NewProject) cleanHandles() error {
	seen := map[string]bool{}
	clean := []string{}
	for _, h := range n.TeamGithubHandles {
		h = strings.ToLower(strings.TrimPrefix(strings.TrimSpace(h), "@"))
		if h == "" || seen[h] {
			continue
		}
		if !githubLogin.MatchString(h) {
			return fmt.Errorf("team_github_handles: %q is not a GitHub account name", h)
		}
		seen[h] = true
		clean = append(clean, h)
	}
	if len(clean) > maxTeamHandles {
		return fmt.Errorf("team_github_handles: list at most %d accounts", maxTeamHandles)
	}
	n.TeamGithubHandles = clean
	return nil
}

func checkURL(label, raw string) error {
	if raw == "" {
		return nil
	}
	u, err := url.Parse(raw)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		return fmt.Errorf("%s must be a full web address starting with http:// or https://", label)
	}
	return nil
}

type Store struct {
	pool *pgxpool.Pool
}

func NewStore(pool *pgxpool.Pool) *Store {
	return &Store{pool: pool}
}

const columns = `id::text, event_id::text, team_name, coalesce(video_url, ''), coalesce(live_url, ''),
	coalesce(repo_url, ''), coalesce(test_login_ref, ''), team_github_handles, status, coalesce(status_detail, ''),
	created_at, updated_at`

func scan(row pgx.Row) (Project, error) {
	var p Project
	err := row.Scan(&p.ID, &p.EventID, &p.TeamName, &p.VideoURL, &p.LiveURL, &p.RepoURL,
		&p.TestLoginRef, &p.TeamGithubHandles, &p.Status, &p.StatusDetail, &p.CreatedAt, &p.UpdatedAt)
	return p, err
}

// Create adds a project to an event. The caller must already have checked that the user owns the event.
func (s *Store) Create(ctx context.Context, eventID string, n NewProject) (Project, error) {
	p, err := scan(s.pool.QueryRow(ctx, `
		INSERT INTO projects (event_id, team_name, video_url, live_url, repo_url, test_login_ref, team_github_handles, abstract)
		VALUES ($1::uuid, $2, NULLIF($3, ''), NULLIF($4, ''), NULLIF($5, ''), NULLIF($6, ''), coalesce($7::text[], '{}'), $8)
		RETURNING `+columns, eventID, n.TeamName, n.VideoURL, n.LiveURL, n.RepoURL, n.TestLoginRef, n.TeamGithubHandles,
		strings.TrimSpace(n.Abstract)))
	if err != nil {
		return Project{}, fmt.Errorf("create project: %w", err)
	}
	return p, nil
}

// Get returns one project. The caller must already have checked ownership.
func (s *Store) Get(ctx context.Context, id string) (Project, error) {
	p, err := scan(s.pool.QueryRow(ctx, `SELECT `+columns+` FROM projects WHERE id = $1::uuid`, id))
	if errors.Is(err, pgx.ErrNoRows) {
		return Project{}, ErrNotFound
	}
	if err != nil {
		return Project{}, fmt.Errorf("get project: %w", err)
	}
	return p, nil
}

// ListForEvent returns every project of an event. The caller must already have checked ownership.
func (s *Store) ListForEvent(ctx context.Context, eventID string) ([]Project, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT `+columns+` FROM projects WHERE event_id = $1::uuid ORDER BY created_at, team_name`, eventID)
	if err != nil {
		return nil, fmt.Errorf("list projects: %w", err)
	}
	defer rows.Close()
	out := []Project{}
	for rows.Next() {
		p, err := scan(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, rows.Err()
}

// NextRun says which run number a new check of this project should use, and whether a check is
// still going. Run 1 is the first check; a re-run is the next number. Jobs of different runs
// never mix, so a re-run keeps the old results beside the new ones.
func (s *Store) NextRun(ctx context.Context, pipeline, projectID string) (run int, active bool, err error) {
	err = s.pool.QueryRow(ctx, `
		SELECT coalesce(max(run_number), 0) + 1,
		       coalesce(bool_or(status IN ('queued', 'running', 'retrying')), false)
		  FROM jobs WHERE pipeline = $1 AND target_id = $2::uuid`, pipeline, projectID).Scan(&run, &active)
	if err != nil {
		return 0, false, fmt.Errorf("find next run: %w", err)
	}
	return run, active, nil
}
