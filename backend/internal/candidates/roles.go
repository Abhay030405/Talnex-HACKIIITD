package candidates

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

// ErrRoleNotFound means the role does not exist or belongs to someone else (the two are never told apart).
var ErrRoleNotFound = errors.New("role not found")

const (
	maxRoleTitle    = 120
	maxJobText      = 20000
	maxPersonText   = 2000
	maxSkills       = 30
	maxSkillChars   = 60
	maxRoleCriteria = 12
)

// Checks a role can switch on or off. An empty set means every check runs.
var validChecks = map[string]bool{"live_test": true, "code_review": true, "coding_profiles": true, "linkedin": true}

// Criterion is one judging criterion with its weight, as on a fixed-problem hackathon.
type Criterion struct {
	Name        string  `json:"name"`
	Description string  `json:"description"`
	Weight      float64 `json:"weight"`
}

// NewRole is a job opening as the recruiter types it.
type NewRole struct {
	Title          string          `json:"title"`
	JobDescription string          `json:"job_description"`
	PersonWanted   string          `json:"person_wanted"`
	Skills         []string        `json:"skills"`
	RoleLevel      string          `json:"role_level"`
	Criteria       []Criterion     `json:"criteria"`
	Checks         map[string]bool `json:"checks"`
	AutoConfirm    *bool           `json:"auto_confirm"`
}

// Role is a saved job opening. Candidates is filled only when one role is read.
type Role struct {
	ID             string          `json:"id"`
	Title          string          `json:"title"`
	JobDescription string          `json:"job_description"`
	PersonWanted   string          `json:"person_wanted"`
	Skills         []string        `json:"skills"`
	RoleLevel      string          `json:"role_level"`
	Criteria       []Criterion     `json:"criteria"`
	Checks         map[string]bool `json:"checks"`
	AutoConfirm    bool            `json:"auto_confirm"`
	CandidateCount int             `json:"candidate_count"`
	CreatedAt      time.Time       `json:"created_at"`
	Candidates     []Candidate     `json:"candidates,omitempty"`
}

func clean(s string) string { return strings.Join(strings.Fields(s), " ") }

// Validate tidies the input and returns a plain-words problem, or nil.
func (n *NewRole) Validate() error {
	n.Title = clean(n.Title)
	n.JobDescription = strings.TrimSpace(n.JobDescription)
	n.PersonWanted = strings.TrimSpace(n.PersonWanted)
	switch {
	case n.Title == "":
		return errors.New("give the role a title")
	case len([]rune(n.Title)) > maxRoleTitle:
		return errors.New("the role title is too long")
	case len([]rune(n.JobDescription)) > maxJobText:
		return fmt.Errorf("the job description is longer than %d characters", maxJobText)
	case len([]rune(n.PersonWanted)) > maxPersonText:
		return fmt.Errorf("the description of the person wanted is longer than %d characters", maxPersonText)
	}
	if n.RoleLevel == "" {
		n.RoleLevel = "fresher"
	}
	if !validLevels[n.RoleLevel] {
		return errors.New("role_level must be fresher, junior, mid or senior")
	}
	skills, seen := []string{}, map[string]bool{}
	for _, s := range n.Skills {
		s = clean(s)
		if s == "" || seen[strings.ToLower(s)] {
			continue
		}
		if len([]rune(s)) > maxSkillChars {
			return fmt.Errorf("the skill %q is too long", s)
		}
		seen[strings.ToLower(s)] = true
		skills = append(skills, s)
	}
	if len(skills) > maxSkills {
		return fmt.Errorf("at most %d skills", maxSkills)
	}
	n.Skills = skills
	if len(n.Criteria) > maxRoleCriteria {
		return fmt.Errorf("at most %d criteria", maxRoleCriteria)
	}
	names := map[string]bool{}
	for i, c := range n.Criteria {
		c.Name, c.Description = clean(c.Name), strings.TrimSpace(c.Description)
		if c.Name == "" {
			return errors.New("every criterion needs a name")
		}
		if names[strings.ToLower(c.Name)] {
			return fmt.Errorf("two criteria are called %q", c.Name)
		}
		if c.Weight <= 0 || c.Weight > 1000 {
			return fmt.Errorf("the weight of %q must be more than 0", c.Name)
		}
		names[strings.ToLower(c.Name)] = true
		n.Criteria[i] = c
	}
	if n.Checks == nil {
		n.Checks = map[string]bool{}
	}
	for k := range n.Checks {
		if !validChecks[k] {
			return fmt.Errorf("unknown check %q (use live_test, code_review, coding_profiles or linkedin)", k)
		}
	}
	return nil
}

// CreateRole saves a role and its criteria in one step.
func (s *Store) CreateRole(ctx context.Context, ownerID string, n NewRole) (Role, error) {
	checks, err := json.Marshal(n.Checks)
	if err != nil {
		return Role{}, err
	}
	auto := n.AutoConfirm == nil || *n.AutoConfirm
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return Role{}, err
	}
	defer tx.Rollback(ctx)
	var id string
	if err := tx.QueryRow(ctx, `
		INSERT INTO roles (owner_id, title, job_description, person_wanted, skills, role_level, checks, auto_confirm)
		VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::jsonb, $8) RETURNING id::text`,
		ownerID, n.Title, n.JobDescription, n.PersonWanted, n.Skills, n.RoleLevel, checks, auto).Scan(&id); err != nil {
		return Role{}, fmt.Errorf("create role: %w", err)
	}
	for _, c := range n.Criteria {
		if _, err := tx.Exec(ctx, `INSERT INTO criteria (role_id, name, description, weight) VALUES ($1::uuid, $2, NULLIF($3, ''), $4)`,
			id, c.Name, c.Description, c.Weight); err != nil {
			return Role{}, fmt.Errorf("save criterion: %w", err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return Role{}, err
	}
	return s.GetRole(ctx, ownerID, id)
}

const roleColumns = `r.id::text, r.title, r.job_description, r.person_wanted, r.skills, r.role_level, r.checks, r.auto_confirm,
	r.created_at, (SELECT count(*) FROM candidates c WHERE c.role_id = r.id)`

func scanRole(row pgx.Row) (Role, error) {
	var (
		r      Role
		checks []byte
	)
	if err := row.Scan(&r.ID, &r.Title, &r.JobDescription, &r.PersonWanted, &r.Skills, &r.RoleLevel, &checks, &r.AutoConfirm,
		&r.CreatedAt, &r.CandidateCount); err != nil {
		return Role{}, err
	}
	r.Checks = map[string]bool{}
	if err := json.Unmarshal(checks, &r.Checks); err != nil {
		return Role{}, fmt.Errorf("read checks: %w", err)
	}
	return r, nil
}

// GetRole reads one of the owner's roles with its criteria and candidates.
func (s *Store) GetRole(ctx context.Context, ownerID, id string) (Role, error) {
	r, err := scanRole(s.pool.QueryRow(ctx, `SELECT `+roleColumns+` FROM roles r WHERE r.id = $1::uuid AND r.owner_id = $2::uuid`, id, ownerID))
	if errors.Is(err, pgx.ErrNoRows) {
		return Role{}, ErrRoleNotFound
	}
	if err != nil {
		return Role{}, fmt.Errorf("read role: %w", err)
	}
	rows, err := s.pool.Query(ctx, `SELECT name, coalesce(description, ''), weight::float8 FROM criteria WHERE role_id = $1::uuid ORDER BY weight DESC, name`, id)
	if err != nil {
		return Role{}, fmt.Errorf("read criteria: %w", err)
	}
	r.Criteria, err = pgx.CollectRows(rows, func(row pgx.CollectableRow) (Criterion, error) {
		var c Criterion
		return c, row.Scan(&c.Name, &c.Description, &c.Weight)
	})
	if err != nil {
		return Role{}, err
	}
	cands, err := s.pool.Query(ctx, `SELECT `+columns+` FROM candidates WHERE role_id = $1::uuid ORDER BY created_at`, id)
	if err != nil {
		return Role{}, fmt.Errorf("read role candidates: %w", err)
	}
	defer cands.Close()
	r.Candidates = []Candidate{}
	for cands.Next() {
		c, err := scan(cands)
		if err != nil {
			return Role{}, err
		}
		r.Candidates = append(r.Candidates, c)
	}
	return r, cands.Err()
}

// ListRoles is the owner's roles, newest first, without criteria or candidates.
func (s *Store) ListRoles(ctx context.Context, ownerID string) ([]Role, error) {
	rows, err := s.pool.Query(ctx, `SELECT `+roleColumns+` FROM roles r WHERE r.owner_id = $1::uuid ORDER BY r.created_at DESC`, ownerID)
	if err != nil {
		return nil, fmt.Errorf("list roles: %w", err)
	}
	defer rows.Close()
	out := []Role{}
	for rows.Next() {
		r, err := scanRole(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

// roleLevelOf is the role's level when the owner owns it, for a candidate created under it.
func (s *Store) roleLevelOf(ctx context.Context, ownerID, roleID string) (string, error) {
	var level string
	err := s.pool.QueryRow(ctx, `SELECT role_level FROM roles WHERE id = $1::uuid AND owner_id = $2::uuid`, roleID, ownerID).Scan(&level)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", ErrRoleNotFound
	}
	return level, err
}

// AutoConfirmRole says whether the candidate's role starts the checks without the confirm page.
func (s *Store) AutoConfirmRole(ctx context.Context, candidateID string) (bool, error) {
	var auto *bool
	err := s.pool.QueryRow(ctx, `SELECT r.auto_confirm FROM candidates c LEFT JOIN roles r ON r.id = c.role_id WHERE c.id = $1::uuid`,
		candidateID).Scan(&auto)
	if errors.Is(err, pgx.ErrNoRows) {
		return false, ErrNotFound
	}
	return auto != nil && *auto, err
}
