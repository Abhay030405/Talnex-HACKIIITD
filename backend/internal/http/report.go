package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
)

// ProofLinks makes short-lived view links for stored screenshots. The r2 Store does this.
type ProofLinks interface {
	ViewLink(ctx context.Context, key string) (string, error)
}

// getReport returns the recruiter proof report of one candidate. The owner only; a stranger gets
// "not found". Every step's `proof_key` is replaced by a short-lived `proof_url`, so raw storage
// keys never leave the server.
func (s *server) getReport(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	id := r.PathValue("id")
	owns, err := auth.OwnsCandidate(r.Context(), s.opts.Pool, who.UserID, id)
	if err != nil {
		s.fail(w, "check candidate owner", err)
		return
	}
	if !owns {
		writeError(w, http.StatusNotFound, "candidate not found")
		return
	}

	var raw []byte
	var hasGaps bool
	var generatedAt time.Time
	err = s.opts.Pool.QueryRow(r.Context(),
		`SELECT report, has_gaps, generated_at FROM candidate_reports WHERE candidate_id = $1::uuid`, id).
		Scan(&raw, &hasGaps, &generatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "the report is not ready yet")
		return
	}
	if err != nil {
		s.fail(w, "read report", err)
		return
	}
	var report map[string]any
	if err := json.Unmarshal(raw, &report); err != nil {
		s.fail(w, "decode report", err)
		return
	}
	report["has_gaps"] = hasGaps
	report["generated_at"] = generatedAt.UTC().Format(time.RFC3339)
	// The coding signals are read fresh, so re-running only the coding checks updates just that part of the report.
	if fresh, err := s.codingSignals(r.Context(), id); err == nil {
		report["coding_signals"] = fresh
	} else {
		s.opts.Log.Warn("read fresh coding signals", "err", err)
	}
	s.swapProofKeys(r.Context(), report)
	writeJSON(w, http.StatusOK, report)
}

// swapProofKeys walks projects[].features[].proof[] and turns each proof_key into a proof_url.
// The key is always removed. Without a link maker, or when a link cannot be made, the url is left out.
func (s *server) swapProofKeys(ctx context.Context, report map[string]any) {
	projects, _ := report["projects"].([]any)
	for _, p := range projects {
		project, _ := p.(map[string]any)
		features, _ := project["features"].([]any)
		for _, f := range features {
			feature, _ := f.(map[string]any)
			steps, _ := feature["proof"].([]any)
			for _, st := range steps {
				step, _ := st.(map[string]any)
				if step == nil {
					continue
				}
				key, _ := step["proof_key"].(string)
				delete(step, "proof_key")
				if key == "" || s.opts.ProofLinks == nil {
					continue
				}
				link, err := s.opts.ProofLinks.ViewLink(ctx, key)
				if err != nil {
					s.opts.Log.Error("make proof link", "err", err)
					continue
				}
				step["proof_url"] = link
			}
		}
	}
}

// codingSignals is the candidate's current coding_signals rows, in the shape the report uses.
func (s *server) codingSignals(ctx context.Context, candidateID string) ([]map[string]any, error) {
	rows, err := s.opts.Pool.Query(ctx, `
		SELECT site, signal, weight, contest, problem, evidence FROM coding_signals
		 WHERE candidate_id = $1::uuid ORDER BY created_at, id`, candidateID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []map[string]any{}
	for rows.Next() {
		var (
			site, signal, weight string
			contest, problem     *string
			evidence             []byte
		)
		if err := rows.Scan(&site, &signal, &weight, &contest, &problem, &evidence); err != nil {
			return nil, err
		}
		var ev map[string]any
		if len(evidence) > 0 {
			_ = json.Unmarshal(evidence, &ev)
		}
		if ev == nil {
			ev = map[string]any{}
		}
		out = append(out, map[string]any{"site": site, "signal": signal, "weight": weight, "contest": contest,
			"problem": problem, "evidence": ev})
	}
	return out, rows.Err()
}
