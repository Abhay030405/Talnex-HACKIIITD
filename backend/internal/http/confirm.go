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
	run, projectIDs, err := pipeline.StartChecks(r.Context(), s.candidates, s.queue, id, in)
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
	writeJSON(w, http.StatusAccepted, map[string]any{"candidate_id": id, "run": run, "projects": len(projectIDs)})
}
