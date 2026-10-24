package candidates

import (
	"context"
	"errors"
	"fmt"
	"strings"
)

// ErrRunning means a delete was refused because some job of the candidate is still going.
var ErrRunning = errors.New("this check is still running; wait for it to finish")

// Stage is one step of the check and where it stands. Note is a short plain reason, only for a failed stage.
type Stage struct {
	Name  string `json:"name"`
	State string `json:"state"`
	Note  string `json:"note,omitempty"`
}

type ProjectProgress struct {
	ID     string  `json:"id"`
	Name   string  `json:"name"`
	Stages []Stage `json:"stages"`
}

type Progress struct {
	Status       string            `json:"status"`
	StatusDetail string            `json:"status_detail"`
	Stages       []Stage           `json:"stages"`
	Projects     []ProjectProgress `json:"projects"`
	ReportReady  bool              `json:"report_ready"`
}

// The order stages are shown in. A stage with no job yet is left out.
var candidateStageOrder = []string{"resume_read", "codeforces", "codechef", "leetcode", "candidate_report", "resume_cleanup"}
var candidatePipelines = []string{"recruiter_candidate", "recruiter_coding", "recruiter_report"}
var projectStageOrder = []string{"precheck", "claims", "github_check", "test_plan", "live_test", "proof_check",
	"feature_score", "originality", "project_summary"}

var stateOf = map[string]string{
	"queued": "waiting", "running": "running", "retrying": "retrying", "done": "done", "failed": "failed",
}

const maxNote = 200

// note makes the failure reason short and one line. Job inputs and results are never read here.
func note(s string) string {
	s = strings.Join(strings.Fields(s), " ")
	if len(s) > maxNote {
		s = s[:maxNote]
	}
	return s
}

type latestJob struct{ state, errText string }

// latestJobs returns, per target and stage, the job of the newest run.
func (s *Store) latestJobs(ctx context.Context, candidateID string) (map[string]map[string]latestJob, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT DISTINCT ON (j.target_id, j.job_type)
		       j.target_id::text, j.job_type, j.status, coalesce(j.error, '')
		  FROM jobs j
		 WHERE (j.target_id = $1::uuid AND j.pipeline = ANY($2)
		    OR j.target_id IN (SELECT id FROM candidate_projects WHERE candidate_id = $1::uuid))
		   -- Only the newest check: a stage not started yet in a re-check must not show the old run's result.
		   AND j.run_number = (SELECT coalesce(max(run_number), 1) FROM jobs
		                        WHERE pipeline = 'recruiter_candidate' AND target_id = $1::uuid)
		 ORDER BY j.target_id, j.job_type, j.run_number DESC, j.created_at DESC`, candidateID, candidatePipelines)
	if err != nil {
		return nil, fmt.Errorf("read progress: %w", err)
	}
	defer rows.Close()
	out := map[string]map[string]latestJob{}
	for rows.Next() {
		var target, stage, status, errText string
		if err := rows.Scan(&target, &stage, &status, &errText); err != nil {
			return nil, err
		}
		if out[target] == nil {
			out[target] = map[string]latestJob{}
		}
		out[target][stage] = latestJob{state: stateOf[status], errText: errText}
	}
	return out, rows.Err()
}

func stagesInOrder(order []string, jobs map[string]latestJob) []Stage {
	out := []Stage{}
	for _, name := range order {
		j, ok := jobs[name]
		if !ok || j.state == "" {
			continue
		}
		st := Stage{Name: name, State: j.state}
		if j.state == "failed" {
			st.Note = note(j.errText)
		}
		out = append(out, st)
	}
	return out
}

// Progress reports where a candidate's check stands. The caller has already checked the owner.
func (s *Store) Progress(ctx context.Context, candidateID string) (Progress, error) {
	var p Progress
	err := s.pool.QueryRow(ctx, `
		SELECT status, coalesce(status_detail, ''),
		       EXISTS (SELECT 1 FROM candidate_reports WHERE candidate_id = $1::uuid)
		  FROM candidates WHERE id = $1::uuid`, candidateID).Scan(&p.Status, &p.StatusDetail, &p.ReportReady)
	if err != nil {
		return Progress{}, fmt.Errorf("read candidate status: %w", err)
	}
	jobs, err := s.latestJobs(ctx, candidateID)
	if err != nil {
		return Progress{}, err
	}
	p.Stages = stagesInOrder(candidateStageOrder, jobs[candidateID])
	p.Projects = []ProjectProgress{}
	rows, err := s.pool.Query(ctx,
		`SELECT id::text, name FROM candidate_projects WHERE candidate_id = $1::uuid ORDER BY created_at, id`, candidateID)
	if err != nil {
		return Progress{}, fmt.Errorf("read projects: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var pp ProjectProgress
		if err := rows.Scan(&pp.ID, &pp.Name); err != nil {
			return Progress{}, err
		}
		pp.Stages = stagesInOrder(projectStageOrder, jobs[pp.ID])
		p.Projects = append(p.Projects, pp)
	}
	return p, rows.Err()
}

// ProjectIDs lists the ids of the candidate's projects (their screenshots live under screens/<id>/).
func (s *Store) ProjectIDs(ctx context.Context, candidateID string) ([]string, error) {
	rows, err := s.pool.Query(ctx, `SELECT id::text FROM candidate_projects WHERE candidate_id = $1::uuid`, candidateID)
	if err != nil {
		return nil, fmt.Errorf("list project ids: %w", err)
	}
	defer rows.Close()
	ids := []string{}
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

const targetsSQL = `(SELECT $1::uuid UNION SELECT id FROM candidate_projects WHERE candidate_id = $1::uuid)`

// IsRunning says whether any job of the candidate or its projects is still going.
func (s *Store) IsRunning(ctx context.Context, candidateID string) (bool, error) {
	var running bool
	err := s.pool.QueryRow(ctx, `
		SELECT EXISTS (SELECT 1 FROM jobs WHERE status IN ('queued', 'running', 'retrying')
		                  AND target_id IN `+targetsSQL+`)`, candidateID).Scan(&running)
	if err != nil {
		return false, fmt.Errorf("check running jobs: %w", err)
	}
	return running, nil
}

// Delete removes the candidate and everything about it in one transaction. Claims, results, test runs, steps,
// flags, scores, coding signals, sandbox runs, walkthroughs and the report go with the candidate by ON DELETE CASCADE;
// jobs have no foreign key, so they are removed here. Refuses with ErrRunning if a job is still going.
func (s *Store) Delete(ctx context.Context, candidateID string) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin delete: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var locked string
	if err := tx.QueryRow(ctx, `SELECT id::text FROM candidates WHERE id = $1::uuid FOR UPDATE`, candidateID).Scan(&locked); err != nil {
		return ErrNotFound
	}
	var running bool
	if err := tx.QueryRow(ctx, `
		SELECT EXISTS (SELECT 1 FROM jobs WHERE status IN ('queued', 'running', 'retrying')
		                  AND target_id IN `+targetsSQL+`)`, candidateID).Scan(&running); err != nil {
		return fmt.Errorf("check running jobs: %w", err)
	}
	if running {
		return ErrRunning
	}
	if _, err := tx.Exec(ctx, `DELETE FROM jobs WHERE target_id IN `+targetsSQL, candidateID); err != nil {
		return fmt.Errorf("delete jobs: %w", err)
	}
	if _, err := tx.Exec(ctx, `DELETE FROM candidates WHERE id = $1::uuid`, candidateID); err != nil {
		return fmt.Errorf("delete candidate: %w", err)
	}
	return tx.Commit(ctx)
}
