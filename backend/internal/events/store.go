// Package events creates and reads hackathon events.
package events

import (
	"encoding/json"
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("event not found")

var (
	validModes  = map[string]bool{"open_theme": true, "fixed_problem": true}
	validLevels = map[string]bool{"fresher": true, "junior": true, "mid": true, "senior": true}
)

type Event struct {
	ID           string    `json:"id"`
	Name         string    `json:"name"`
	Mode         string    `json:"mode"`
	RoleLevel    string    `json:"role_level"`
	StartsAt     time.Time `json:"starts_at"`
	EndsAt       time.Time `json:"ends_at"`
	SponsorTools []string  `json:"sponsor_tools"`
	// Criteria are the organizer's weighted criteria. Only fixed-problem events have them.
	Criteria  []Criterion `json:"criteria"`
	CreatedAt time.Time   `json:"created_at"`
}

// Criterion is one thing the organizer wants to see, with how much it counts.
type Criterion struct {
	ID          string  `json:"id"`
	Name        string  `json:"name"`
	Description string  `json:"description"`
	Weight      float64 `json:"weight"`
}

type NewCriterion struct {
	Name        string  `json:"name"`
	Description string  `json:"description"`
	Weight      float64 `json:"weight"`
}

type NewEvent struct {
	Name         string         `json:"name"`
	Mode         string         `json:"mode"`
	RoleLevel    string         `json:"role_level"`
	StartsAt     time.Time      `json:"starts_at"`
	EndsAt       time.Time      `json:"ends_at"`
	SponsorTools []string       `json:"sponsor_tools"`
	Criteria     []NewCriterion `json:"criteria"`
	// Brief is the problem statement or theme judges give; it reaches the test prompts as data.
	Brief  string          `json:"brief"`
	Checks map[string]bool `json:"checks"`
}

// Validate returns a plain-words problem with the input, or nil.
func (n *NewEvent) Validate() error {
	n.Name = strings.TrimSpace(n.Name)
	if len([]rune(n.Brief)) > 20000 {
		return errors.New("the brief is longer than 20000 characters")
	}
	if n.Name == "" {
		return errors.New("name is required")
	}
	if !validModes[n.Mode] {
		return errors.New("mode must be open_theme or fixed_problem")
	}
	if n.RoleLevel == "" {
		n.RoleLevel = "fresher"
	}
	if !validLevels[n.RoleLevel] {
		return errors.New("role_level must be fresher, junior, mid or senior")
	}
	if n.StartsAt.IsZero() || n.EndsAt.IsZero() || !n.EndsAt.After(n.StartsAt) {
		return errors.New("starts_at and ends_at are required, and ends_at must be after starts_at")
	}
	if n.SponsorTools == nil {
		n.SponsorTools = []string{}
	}
	return n.validateCriteria()
}

// validateCriteria: a fixed-problem event needs criteria with weights; an open-theme event has none.
func (n *NewEvent) validateCriteria() error {
	if n.Mode == "open_theme" {
		if len(n.Criteria) > 0 {
			return errors.New("criteria are only for fixed_problem events")
		}
		return nil
	}
	if len(n.Criteria) == 0 {
		return errors.New("a fixed_problem event needs at least one criterion")
	}
	seen := map[string]bool{}
	for i := range n.Criteria {
		c := &n.Criteria[i]
		c.Name = strings.TrimSpace(c.Name)
		c.Description = strings.TrimSpace(c.Description)
		if c.Name == "" {
			return fmt.Errorf("criteria: criterion %d has no name", i+1)
		}
		key := strings.ToLower(c.Name)
		if seen[key] {
			return fmt.Errorf("criteria: %q appears twice", c.Name)
		}
		seen[key] = true
		if !(c.Weight > 0) {
			return fmt.Errorf("criteria: %q needs a weight above 0", c.Name)
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

const columns = `id::text, name, mode, role_level, starts_at, ends_at, sponsor_tools, created_at`

func scan(row pgx.Row) (Event, error) {
	var e Event
	err := row.Scan(&e.ID, &e.Name, &e.Mode, &e.RoleLevel, &e.StartsAt, &e.EndsAt, &e.SponsorTools, &e.CreatedAt)
	return e, err
}

func (s *Store) Create(ctx context.Context, ownerID string, n NewEvent) (Event, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return Event{}, fmt.Errorf("create event: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck // a rollback after commit is a no-op
	e, err := scan(tx.QueryRow(ctx, `
		INSERT INTO events (owner_id, name, mode, role_level, starts_at, ends_at, sponsor_tools, brief, checks)
		VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, coalesce($9::jsonb, '{}'))
		RETURNING `+columns, ownerID, n.Name, n.Mode, n.RoleLevel, n.StartsAt, n.EndsAt, n.SponsorTools,
		strings.TrimSpace(n.Brief), checksJSON(n.Checks)))
	if err != nil {
		return Event{}, fmt.Errorf("create event: %w", err)
	}
	e.Criteria = []Criterion{}
	for _, c := range n.Criteria {
		var made Criterion
		err := tx.QueryRow(ctx, `
			INSERT INTO criteria (event_id, name, description, weight) VALUES ($1::uuid, $2, NULLIF($3, ''), $4)
			RETURNING id::text, name, coalesce(description, ''), weight::float8`,
			e.ID, c.Name, c.Description, c.Weight).Scan(&made.ID, &made.Name, &made.Description, &made.Weight)
		if err != nil {
			return Event{}, fmt.Errorf("create criterion: %w", err)
		}
		e.Criteria = append(e.Criteria, made)
	}
	if err := tx.Commit(ctx); err != nil {
		return Event{}, fmt.Errorf("create event: %w", err)
	}
	return e, nil
}

// Get returns an event only if the user owns it.
func (s *Store) Get(ctx context.Context, ownerID, id string) (Event, error) {
	e, err := scan(s.pool.QueryRow(ctx,
		`SELECT `+columns+` FROM events WHERE id = $2::uuid AND owner_id = $1::uuid`, ownerID, id))
	if errors.Is(err, pgx.ErrNoRows) {
		return Event{}, ErrNotFound
	}
	if err != nil {
		return Event{}, fmt.Errorf("get event: %w", err)
	}
	if e.Criteria, err = s.criteria(ctx, e.ID); err != nil {
		return Event{}, err
	}
	return e, nil
}

func (s *Store) criteria(ctx context.Context, eventID string) ([]Criterion, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id::text, name, coalesce(description, ''), weight::float8
		  FROM criteria WHERE event_id = $1::uuid ORDER BY name`, eventID)
	if err != nil {
		return nil, fmt.Errorf("read criteria: %w", err)
	}
	defer rows.Close()
	out := []Criterion{}
	for rows.Next() {
		var c Criterion
		if err := rows.Scan(&c.ID, &c.Name, &c.Description, &c.Weight); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	return out, rows.Err()
}

func (s *Store) List(ctx context.Context, ownerID string) ([]Event, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT `+columns+` FROM events WHERE owner_id = $1::uuid ORDER BY created_at DESC`, ownerID)
	if err != nil {
		return nil, fmt.Errorf("list events: %w", err)
	}
	defer rows.Close()
	out := []Event{}
	for rows.Next() {
		e, err := scan(rows)
		if err != nil {
			return nil, err
		}
		e.Criteria = []Criterion{}
		out = append(out, e)
	}
	return out, rows.Err()
}

// checksJSON stores the chosen checks; nil means every check.
func checksJSON(c map[string]bool) []byte {
	if len(c) == 0 {
		return nil
	}
	b, _ := json.Marshal(c)
	return b
}

// ValidateCriteria checks an edited criteria list with the same rules as event create.
func ValidateCriteria(list []NewCriterion) ([]NewCriterion, error) {
	n := NewEvent{Mode: "fixed_problem", Criteria: list}
	err := n.validateCriteria()
	return n.Criteria, err
}

// ErrNotFixedProblem means the event has no criteria to edit (an open-theme event).
var ErrNotFixedProblem = errors.New("only a fixed_problem event has criteria")

// ReplaceCriteria swaps an event's criteria for an edited list. Results stay; the weighted total re-scores from them.
func (s *Store) ReplaceCriteria(ctx context.Context, eventID string, list []NewCriterion) ([]Criterion, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck // a rollback after commit is a no-op
	var mode string
	if err := tx.QueryRow(ctx, `SELECT mode FROM events WHERE id = $1::uuid`, eventID).Scan(&mode); err != nil {
		return nil, fmt.Errorf("read event: %w", err)
	}
	if mode != "fixed_problem" {
		return nil, ErrNotFixedProblem
	}
	if _, err := tx.Exec(ctx, `DELETE FROM criteria WHERE event_id = $1::uuid`, eventID); err != nil {
		return nil, err
	}
	for _, c := range list {
		if _, err := tx.Exec(ctx, `INSERT INTO criteria (event_id, name, description, weight) VALUES ($1::uuid, $2, NULLIF($3, ''), $4)`,
			eventID, c.Name, c.Description, c.Weight); err != nil {
			return nil, fmt.Errorf("save criterion: %w", err)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return s.criteria(ctx, eventID)
}
