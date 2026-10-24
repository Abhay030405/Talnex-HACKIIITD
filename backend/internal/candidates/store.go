// Package candidates creates and reads recruiter checks.
package candidates

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("candidate not found")

var validLevels = map[string]bool{"fresher": true, "junior": true, "mid": true, "senior": true}

var validSites = map[string]bool{"codeforces": true, "leetcode": true, "codechef": true}

type Candidate struct {
	ID            string            `json:"id"`
	Label         string            `json:"label"`
	RoleLevel     string            `json:"role_level"`
	RoleID        string            `json:"role_id,omitempty"`
	CodingHandles map[string]string `json:"coding_handles"`
	Status        string            `json:"status"`
	CreatedAt     time.Time         `json:"created_at"`
}

type NewCandidate struct {
	Label         string            `json:"label"`
	RoleLevel     string            `json:"role_level"`
	CodingHandles map[string]string `json:"coding_handles"`
	// RoleID puts the candidate under one of the owner's roles; the role's level is then used.
	RoleID string `json:"role_id"`
}

// Validate returns a plain-words problem with the input, or nil.
func (n *NewCandidate) Validate() error {
	n.Label = strings.TrimSpace(n.Label)
	if n.RoleLevel == "" {
		n.RoleLevel = "fresher"
	}
	if !validLevels[n.RoleLevel] {
		return errors.New("role_level must be fresher, junior, mid or senior")
	}
	n.RoleID = strings.TrimSpace(n.RoleID)
	if n.RoleID != "" {
		if _, err := uuid.Parse(n.RoleID); err != nil {
			return errors.New("role_id is not a valid id")
		}
	}
	if n.CodingHandles == nil {
		n.CodingHandles = map[string]string{}
	}
	for site, handle := range n.CodingHandles {
		if !validSites[site] {
			return fmt.Errorf("coding_handles: unknown site %q (use codeforces, leetcode or codechef)", site)
		}
		if strings.TrimSpace(handle) == "" {
			return fmt.Errorf("coding_handles: %s handle is empty", site)
		}
	}
	return nil
}

type Store struct {
	pool *pgxpool.Pool
}

func NewStore(pool *pgxpool.Pool) *Store {
	return &Store{pool: pool}
}

const columns = `id::text, coalesce(label, ''), role_level, coalesce(role_id::text, ''), coding_handles, status, created_at`

func scan(row pgx.Row) (Candidate, error) {
	var (
		c   Candidate
		raw []byte
	)
	if err := row.Scan(&c.ID, &c.Label, &c.RoleLevel, &c.RoleID, &raw, &c.Status, &c.CreatedAt); err != nil {
		return Candidate{}, err
	}
	c.CodingHandles = map[string]string{}
	if err := json.Unmarshal(raw, &c.CodingHandles); err != nil {
		return Candidate{}, fmt.Errorf("read coding handles: %w", err)
	}
	return c, nil
}

func (s *Store) Create(ctx context.Context, ownerID string, n NewCandidate) (Candidate, error) {
	handles, err := json.Marshal(n.CodingHandles)
	if err != nil {
		return Candidate{}, err
	}
	if n.RoleID != "" {
		if n.RoleLevel, err = s.roleLevelOf(ctx, ownerID, n.RoleID); err != nil {
			return Candidate{}, err
		}
	}
	c, err := scan(s.pool.QueryRow(ctx, `
		INSERT INTO candidates (owner_id, label, role_level, coding_handles, role_id)
		VALUES ($1::uuid, NULLIF($2, ''), $3, $4::jsonb, NULLIF($5, '')::uuid)
		RETURNING `+columns, ownerID, n.Label, n.RoleLevel, handles, n.RoleID))
	if err != nil {
		return Candidate{}, fmt.Errorf("create candidate: %w", err)
	}
	return c, nil
}

// NextRun says which run number a new resume read should use, and whether one is still going.
// Run 1 is the first read; uploading a new resume after a failure uses the next number.
func (s *Store) NextRun(ctx context.Context, pipeline, candidateID string) (run int, active bool, err error) {
	err = s.pool.QueryRow(ctx, `
		SELECT coalesce(max(run_number), 0) + 1,
		       coalesce(bool_or(status IN ('queued', 'running', 'retrying')), false)
		  FROM jobs WHERE pipeline = $1 AND target_id = $2::uuid`, pipeline, candidateID).Scan(&run, &active)
	if err != nil {
		return 0, false, fmt.Errorf("find next run: %w", err)
	}
	return run, active, nil
}

// AttachResume records where the resume file is kept and puts the check back to "submitted".
func (s *Store) AttachResume(ctx context.Context, candidateID, key string) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE candidates SET resume_key = $2, resume_deleted_at = NULL, status = 'submitted', status_detail = NULL,
		       updated_at = now()
		 WHERE id = $1::uuid`, candidateID, key)
	if err != nil {
		return fmt.Errorf("attach resume: %w", err)
	}
	return nil
}

// Get returns a candidate only if the user owns it.
func (s *Store) Get(ctx context.Context, ownerID, id string) (Candidate, error) {
	c, err := scan(s.pool.QueryRow(ctx,
		`SELECT `+columns+` FROM candidates WHERE id = $2::uuid AND owner_id = $1::uuid`, ownerID, id))
	if errors.Is(err, pgx.ErrNoRows) {
		return Candidate{}, ErrNotFound
	}
	if err != nil {
		return Candidate{}, fmt.Errorf("get candidate: %w", err)
	}
	return c, nil
}

func (s *Store) List(ctx context.Context, ownerID string) ([]Candidate, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT `+columns+` FROM candidates WHERE owner_id = $1::uuid ORDER BY created_at DESC`, ownerID)
	if err != nil {
		return nil, fmt.Errorf("list candidates: %w", err)
	}
	defer rows.Close()
	out := []Candidate{}
	for rows.Next() {
		c, err := scan(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	return out, rows.Err()
}
