package http

import (
	"errors"
	"net/http"

	"github.com/google/uuid"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/candidates"
)

// Roles are job openings a recruiter checks resumes against (bulk upload: many candidates under one role).

func (s *server) createRole(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	var in candidates.NewRole
	if !decode(w, r, &in) {
		return
	}
	if err := in.Validate(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	role, err := s.candidates.CreateRole(r.Context(), who.UserID, in)
	if err != nil {
		s.fail(w, "create role", err)
		return
	}
	writeJSON(w, http.StatusCreated, role)
}

func (s *server) listRoles(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	list, err := s.candidates.ListRoles(r.Context(), who.UserID)
	if err != nil {
		s.fail(w, "list roles", err)
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func (s *server) getRole(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	id := r.PathValue("id")
	if _, err := uuid.Parse(id); err != nil {
		writeError(w, http.StatusNotFound, "role not found")
		return
	}
	role, err := s.candidates.GetRole(r.Context(), who.UserID, id)
	if errors.Is(err, candidates.ErrRoleNotFound) {
		writeError(w, http.StatusNotFound, "role not found")
		return
	}
	if err != nil {
		s.fail(w, "read role", err)
		return
	}
	writeJSON(w, http.StatusOK, role)
}
