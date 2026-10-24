package http

import (
	"errors"
	"net/http"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/events"
)

// updateCriteria replaces a fixed-problem event's criteria and weights. The owner is checked before the body is read.
func (s *server) updateCriteria(w http.ResponseWriter, r *http.Request) {
	_, eventID, ok := s.ownedEvent(w, r)
	if !ok {
		return
	}
	var in struct {
		Criteria []events.NewCriterion `json:"criteria"`
	}
	if !decode(w, r, &in) {
		return
	}
	list, err := events.ValidateCriteria(in.Criteria)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	saved, err := s.events.ReplaceCriteria(r.Context(), eventID, list)
	if errors.Is(err, events.ErrNotFixedProblem) {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err != nil {
		s.fail(w, "update criteria", err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"criteria": saved})
}
