package http

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/candidates"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/events"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
)

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}

func decode(w http.ResponseWriter, r *http.Request, into any) bool {
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
	dec.DisallowUnknownFields()
	if err := dec.Decode(into); err != nil {
		msg := "the request body is not valid"
		if errors.Is(err, io.EOF) {
			msg = "the request body is empty"
		}
		writeError(w, http.StatusBadRequest, msg)
		return false
	}
	return true
}

func (s *server) fail(w http.ResponseWriter, what string, err error) {
	s.opts.Log.Error(what, "err", err)
	writeError(w, http.StatusInternalServerError, "something went wrong")
}

func (s *server) identity(w http.ResponseWriter, r *http.Request) (auth.Identity, bool) {
	id, ok := auth.From(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "sign in required")
	}
	return id, ok
}

func (s *server) healthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *server) readyz(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()
	if s.opts.Ready != nil {
		if err := s.opts.Ready(ctx); err != nil {
			s.opts.Log.Warn("not ready", "err", err)
			writeError(w, http.StatusServiceUnavailable, "not ready")
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (s *server) me(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": who.UserID, "email": who.Email})
}

// ---- events ----

func (s *server) createEvent(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	var in events.NewEvent
	if !decode(w, r, &in) {
		return
	}
	if err := in.Validate(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	e, err := s.events.Create(r.Context(), who.UserID, in)
	if err != nil {
		s.fail(w, "create event", err)
		return
	}
	writeJSON(w, http.StatusCreated, e)
}

func (s *server) listEvents(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	list, err := s.events.List(r.Context(), who.UserID)
	if err != nil {
		s.fail(w, "list events", err)
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func (s *server) getEvent(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	owns, err := auth.OwnsEvent(r.Context(), s.opts.Pool, who.UserID, r.PathValue("id"))
	if err != nil {
		s.fail(w, "check event owner", err)
		return
	}
	if !owns {
		writeError(w, http.StatusNotFound, "event not found")
		return
	}
	e, err := s.events.Get(r.Context(), who.UserID, r.PathValue("id"))
	if err != nil {
		s.fail(w, "get event", err)
		return
	}
	writeJSON(w, http.StatusOK, e)
}

// ---- candidates ----

func (s *server) createCandidate(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	var in candidates.NewCandidate
	if !decode(w, r, &in) {
		return
	}
	if err := in.Validate(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	c, err := s.candidates.Create(r.Context(), who.UserID, in)
	if errors.Is(err, candidates.ErrRoleNotFound) {
		writeError(w, http.StatusBadRequest, "that role does not exist")
		return
	}
	if err != nil {
		s.fail(w, "create candidate", err)
		return
	}
	writeJSON(w, http.StatusCreated, c)
}

func (s *server) listCandidates(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	list, err := s.candidates.List(r.Context(), who.UserID)
	if err != nil {
		s.fail(w, "list candidates", err)
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func (s *server) getCandidate(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	owns, err := auth.OwnsCandidate(r.Context(), s.opts.Pool, who.UserID, r.PathValue("id"))
	if err != nil {
		s.fail(w, "check candidate owner", err)
		return
	}
	if !owns {
		writeError(w, http.StatusNotFound, "candidate not found")
		return
	}
	c, err := s.candidates.Get(r.Context(), who.UserID, r.PathValue("id"))
	if err != nil {
		s.fail(w, "get candidate", err)
		return
	}
	writeJSON(w, http.StatusOK, c)
}

// ---- dev tools (only when ENABLE_DEV_ENDPOINTS=true) ----

// startSelfTest starts the python -> go -> python test pipeline on a random target.
func (s *server) startSelfTest(w http.ResponseWriter, r *http.Request) {
	target := newUUID()
	ids, err := s.queue.StartPipeline(r.Context(), pipeline.SelfTest, "project", target, 1)
	if err != nil {
		s.fail(w, "start selftest", err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"target": target, "started_jobs": ids})
}

func (s *server) selfTestStatus(w http.ResponseWriter, r *http.Request) {
	rows, err := s.opts.Pool.Query(r.Context(), `
		SELECT job_type, runner, status, tries, coalesce(error, '')
		  FROM jobs WHERE pipeline = $1 AND target_id::text = $2 ORDER BY created_at`,
		pipeline.SelfTest, r.PathValue("target"))
	if err != nil {
		// A malformed id simply has no jobs.
		writeJSON(w, http.StatusOK, []any{})
		return
	}
	defer rows.Close()
	type row struct {
		Type   string `json:"job_type"`
		Runner string `json:"runner"`
		Status string `json:"status"`
		Tries  int    `json:"tries"`
		Error  string `json:"error,omitempty"`
	}
	out := []row{}
	for rows.Next() {
		var x row
		if err := rows.Scan(&x.Type, &x.Runner, &x.Status, &x.Tries, &x.Error); err != nil {
			s.fail(w, "read selftest jobs", err)
			return
		}
		out = append(out, x)
	}
	writeJSON(w, http.StatusOK, out)
}

func newUUID() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}
