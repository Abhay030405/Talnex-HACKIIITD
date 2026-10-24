package http

import (
	"net/http"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
)

// rerunCandidateProject tests one resume project again. The report is rebuilt when it finishes.
func (s *server) rerunCandidateProject(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedCandidateProject(w, r)
	if !ok {
		return
	}
	run, active, err := s.candidates.NextRun(r.Context(), pipeline.Recruiter, id)
	if err != nil {
		s.fail(w, "find next run", err)
		return
	}
	if active {
		writeError(w, http.StatusConflict, "this project is still being checked")
		return
	}
	if _, err := s.queue.StartPipeline(r.Context(), pipeline.Recruiter, "candidate_project", id, run); err != nil {
		s.fail(w, "start project check", err)
		return
	}
	if _, err := s.opts.Pool.Exec(r.Context(), `
		UPDATE candidates SET status = 'testing', status_detail = NULL, updated_at = now()
		 WHERE id = (SELECT candidate_id FROM candidate_projects WHERE id = $1::uuid)`, id); err != nil {
		s.fail(w, "mark testing", err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"candidate_project_id": id, "run": run})
}

// rerunCoding reads the coding profiles again, then rebuilds the report (the report waits for these checks).
func (s *server) rerunCoding(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedCandidate(w, r)
	if !ok {
		return
	}
	coding, active, err := s.candidates.NextRun(r.Context(), pipeline.RecruiterCoding, id)
	if err != nil {
		s.fail(w, "find next run", err)
		return
	}
	if active {
		writeError(w, http.StatusConflict, "the coding checks are still running")
		return
	}
	report, _, err := s.candidates.NextRun(r.Context(), pipeline.RecruiterReport, id)
	if err != nil {
		s.fail(w, "find next run", err)
		return
	}
	run := max(coding, report) // one run number, so the report waits for exactly these coding checks
	for _, p := range []string{pipeline.RecruiterCoding, pipeline.RecruiterReport} {
		if _, err := s.queue.StartPipeline(r.Context(), p, "candidate", id, run); err != nil {
			s.fail(w, "start "+p, err)
			return
		}
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"candidate_id": id, "run": run})
}
