package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
)

// The jobs panel: every job of a subject, retrying a failed one, and running chosen stages again.

type jobRow struct {
	ID         string          `json:"id"`
	Pipeline   string          `json:"pipeline"`
	Stage      string          `json:"stage"`
	TargetType string          `json:"target_type"`
	TargetID   string          `json:"target_id"`
	Project    string          `json:"project,omitempty"`
	Run        int             `json:"run"`
	Status     string          `json:"status"`
	Tries      int             `json:"tries"`
	MaxTries   int             `json:"max_tries"`
	Created    time.Time       `json:"created_at"`
	Updated    time.Time       `json:"updated_at"`
	Seconds    float64         `json:"seconds"`
	Error      string          `json:"error,omitempty"`
	Result     json.RawMessage `json:"result,omitempty"`
}

// Report-answer and custom-test jobs belong to the chat, not the panel.
const jobColumns = `j.id::text, coalesce(j.pipeline, ''), j.job_type, j.target_type, j.target_id::text, coalesce(cp.name, ''),
	j.run_number, j.status, j.tries, j.max_tries, j.created_at, j.updated_at,
	extract(epoch FROM j.updated_at - j.created_at)::float8, coalesce(j.error, ''), j.result`

func (s *server) listJobs(w http.ResponseWriter, r *http.Request, where string, id string) {
	rows, err := s.opts.Pool.Query(r.Context(), `SELECT `+jobColumns+` FROM jobs j
		LEFT JOIN candidate_projects cp ON cp.id = j.target_id
		WHERE j.pipeline IS NOT NULL AND (`+where+`)
		ORDER BY j.run_number DESC, j.created_at LIMIT 400`, id)
	if err != nil {
		s.fail(w, "list jobs", err)
		return
	}
	list, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (jobRow, error) {
		var j jobRow
		var result []byte
		err := row.Scan(&j.ID, &j.Pipeline, &j.Stage, &j.TargetType, &j.TargetID, &j.Project, &j.Run, &j.Status,
			&j.Tries, &j.MaxTries, &j.Created, &j.Updated, &j.Seconds, &j.Error, &result)
		j.Error = firstLine(j.Error)
		if len(result) > 0 && len(result) <= 2000 {
			j.Result = result
		}
		return j, err
	})
	if err != nil {
		s.fail(w, "read jobs", err)
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func firstLine(s string) string {
	s, _, _ = strings.Cut(strings.TrimSpace(s), "\n")
	if len(s) > 200 {
		s = s[:200]
	}
	return s
}

func (s *server) listCandidateJobs(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedCandidate(w, r)
	if !ok {
		return
	}
	s.listJobs(w, r, `j.target_id = $1::uuid OR j.target_id IN (SELECT id FROM candidate_projects WHERE candidate_id = $1::uuid)`, id)
}

func (s *server) listProjectJobs(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedProject(w, r)
	if !ok {
		return
	}
	s.listJobs(w, r, `j.target_id = $1::uuid`, id)
}

// ownsJobTarget checks the caller owns what the job is about.
func (s *server) ownsJobTarget(ctx context.Context, userID, targetType, targetID string) (bool, error) {
	switch targetType {
	case "candidate":
		return auth.OwnsCandidate(ctx, s.opts.Pool, userID, targetID)
	case "candidate_project":
		return auth.OwnsCandidateProject(ctx, s.opts.Pool, userID, targetID)
	case "project":
		return auth.OwnsProject(ctx, s.opts.Pool, userID, targetID)
	case "event":
		return auth.OwnsEvent(ctx, s.opts.Pool, userID, targetID)
	}
	return false, nil
}

// retryJob puts one failed job back in the queue, in its own run.
func (s *server) retryJob(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	id := r.PathValue("id")
	if _, err := uuid.Parse(id); err != nil {
		writeError(w, http.StatusNotFound, "job not found")
		return
	}
	var targetType, targetID string
	err := s.opts.Pool.QueryRow(r.Context(), `SELECT target_type, target_id::text FROM jobs WHERE id = $1::uuid`, id).Scan(&targetType, &targetID)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "job not found")
		return
	}
	if err != nil {
		s.fail(w, "read job", err)
		return
	}
	owns, err := s.ownsJobTarget(r.Context(), who.UserID, targetType, targetID)
	if err != nil {
		s.fail(w, "check job owner", err)
		return
	}
	if !owns {
		writeError(w, http.StatusNotFound, "job not found")
		return
	}
	done, err := pipeline.RetryFailed(r.Context(), s.opts.Pool, id)
	if err != nil {
		s.fail(w, "retry job", err)
		return
	}
	if !done {
		writeError(w, http.StatusConflict, "only a failed job can be retried")
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": id})
}

type stagesBody struct {
	Stages []string `json:"stages"`
}

// runStages is the shared body of the three run-stages routes. status, when set, is the status the subject is moved to.
func (s *server) runStages(w http.ResponseWriter, r *http.Request, pipe, targetType, id, status string) {
	var in stagesBody
	if !decode(w, r, &in) {
		return
	}
	run, queued, err := pipeline.RunStages(r.Context(), s.opts.Pool, pipe, targetType, id, in.Stages)
	var bad pipeline.ErrBadStages
	switch {
	case errors.As(err, &bad):
		writeError(w, http.StatusBadRequest, bad.Error())
		return
	case errors.Is(err, pipeline.ErrBusy):
		writeError(w, http.StatusConflict, err.Error())
		return
	case err != nil:
		s.fail(w, "run stages", err)
		return
	}
	if status != "" {
		if _, err := s.opts.Pool.Exec(r.Context(), status, id); err != nil {
			s.fail(w, "mark running", err)
			return
		}
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"run": run, "queued": queued})
}

func (s *server) runCandidateProjectStages(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedCandidateProject(w, r)
	if !ok {
		return
	}
	s.runStages(w, r, pipeline.Recruiter, "candidate_project", id, `
		UPDATE candidates SET status = 'testing', status_detail = NULL, updated_at = now()
		 WHERE id = (SELECT candidate_id FROM candidate_projects WHERE id = $1::uuid)`)
}

func (s *server) runCandidateStages(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedCandidate(w, r)
	if !ok {
		return
	}
	s.runStages(w, r, pipeline.RecruiterCoding, "candidate", id, "")
}

func (s *server) runProjectStages(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedProject(w, r)
	if !ok {
		return
	}
	s.runStages(w, r, pipeline.Hackathon, "project", id, `UPDATE projects SET status = 'testing', updated_at = now() WHERE id = $1::uuid`)
}
