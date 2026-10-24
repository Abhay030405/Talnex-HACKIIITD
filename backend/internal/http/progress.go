package http

import (
	"context"
	"errors"
	"net/http"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/candidates"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/storage/r2"
)

// FileRemover deletes every stored file under a folder. The r2 Store does this.
type FileRemover interface {
	DeletePrefix(ctx context.Context, prefix string) error
}

// ownedCandidate answers 401/404 itself and returns the id only for the owner.
func (s *server) ownedCandidate(w http.ResponseWriter, r *http.Request) (string, bool) {
	who, ok := s.identity(w, r)
	if !ok {
		return "", false
	}
	id := r.PathValue("id")
	owns, err := auth.OwnsCandidate(r.Context(), s.opts.Pool, who.UserID, id)
	if err != nil {
		s.fail(w, "check candidate owner", err)
		return "", false
	}
	if !owns {
		writeError(w, http.StatusNotFound, "candidate not found")
		return "", false
	}
	return id, true
}

// getProgress shows where each stage of a candidate's check stands. The owner only.
func (s *server) getProgress(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedCandidate(w, r)
	if !ok {
		return
	}
	p, err := s.candidates.Progress(r.Context(), id)
	if err != nil {
		s.fail(w, "read progress", err)
		return
	}
	writeJSON(w, http.StatusOK, p)
}

// deleteCandidate removes a candidate and everything about it: stored files first, then the rows in one step.
func (s *server) deleteCandidate(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedCandidate(w, r)
	if !ok {
		return
	}
	running, err := s.candidates.IsRunning(r.Context(), id)
	if err != nil {
		s.fail(w, "check running jobs", err)
		return
	}
	if running {
		writeError(w, http.StatusConflict, candidates.ErrRunning.Error())
		return
	}
	if s.opts.FileRemover != nil {
		projectIDs, err := s.candidates.ProjectIDs(r.Context(), id)
		if err != nil {
			s.fail(w, "list projects", err)
			return
		}
		prefixes := []string{r2.ResumePrefix(id)}
		for _, p := range projectIDs {
			prefixes = append(prefixes, "screens/"+p+"/")
		}
		for _, prefix := range prefixes {
			if err := s.opts.FileRemover.DeletePrefix(r.Context(), prefix); err != nil {
				s.fail(w, "delete stored files", err)
				return
			}
		}
	}
	switch err := s.candidates.Delete(r.Context(), id); {
	case errors.Is(err, candidates.ErrRunning):
		writeError(w, http.StatusConflict, candidates.ErrRunning.Error())
	case errors.Is(err, candidates.ErrNotFound):
		writeError(w, http.StatusNotFound, "candidate not found")
	case err != nil:
		s.fail(w, "delete candidate", err)
	default:
		w.WriteHeader(http.StatusNoContent)
	}
}
