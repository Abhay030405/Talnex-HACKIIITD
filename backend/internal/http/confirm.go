package http

import (
	"errors"
	"net/http"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/candidates"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
)

// getFound shows what the resume reader found, for the recruiter to confirm. The owner only.
func (s *server) getFound(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedCandidate(w, r)
	if !ok {
		return
	}
	found, err := s.candidates.Found(r.Context(), id)
	if err != nil {
		s.fail(w, "read what was found", err)
		return
	}
	writeJSON(w, http.StatusOK, found)
}

// confirmCandidate takes the recruiter's final list of projects and coding profiles and starts the checks.
// It can be sent again if the first call failed half way: starting a pipeline twice adds no second set of jobs.
func (s *server) confirmCandidate(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedCandidate(w, r)
	if !ok {
		return
	}
	var in candidates.Confirmation
	if !decode(w, r, &in) {
		return
	}
	projectIDs, err := s.candidates.Confirm(r.Context(), id, in)
	var bad candidates.ErrBadInput
	switch {
	case errors.As(err, &bad):
		writeError(w, http.StatusBadRequest, bad.Error())
		return
	case errors.Is(err, candidates.ErrNotWaiting):
		writeError(w, http.StatusConflict, err.Error())
		return
	case err != nil:
		s.fail(w, "confirm candidate", err)
		return
	}
	run, err := s.candidates.ReadRun(r.Context(), id)
	if err != nil {
		s.fail(w, "find run", err)
		return
	}
	if _, err := s.queue.StartPipeline(r.Context(), pipeline.RecruiterCoding, "candidate", id, run); err != nil {
		s.fail(w, "start coding checks", err)
		return
	}
	for _, projectID := range projectIDs {
		if _, err := s.queue.StartPipeline(r.Context(), pipeline.Recruiter, "candidate_project", projectID, run); err != nil {
			s.fail(w, "start project check", err)
			return
		}
	}
	if err := s.candidates.MarkStarted(r.Context(), id); err != nil {
		s.fail(w, "mark started", err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"candidate_id": id, "run": run, "projects": len(projectIDs)})
}
