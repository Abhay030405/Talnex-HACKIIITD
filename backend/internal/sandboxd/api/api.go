// Package api is the HTTP face of sandboxd. Every route except /healthz needs the token. It is the whole of sandboxd's
// interface (architecture section 28.3): create a VM, upload files, run a command, list ports, send an HTTP request
// to the app inside, destroy the VM, and check health.
package api

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/sandboxd"
)

// NewHandler builds the routes. token must not be empty.
func NewHandler(m *sandboxd.Manager, driver, token string, log *slog.Logger) http.Handler {
	if log == nil {
		log = slog.Default()
	}
	s := &server{m: m, driver: driver, log: log}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/vms", s.create)
	mux.HandleFunc("GET /v1/vms", s.list)
	mux.HandleFunc("DELETE /v1/vms/{id}", s.destroy)
	mux.HandleFunc("POST /v1/vms/{id}/files", s.upload)
	mux.HandleFunc("POST /v1/vms/{id}/exec", s.exec)
	mux.HandleFunc("GET /v1/vms/{id}/ports", s.ports)
	mux.HandleFunc("POST /v1/vms/{id}/request", s.request)

	root := http.NewServeMux()
	root.HandleFunc("GET /healthz", s.healthz)
	root.Handle("/", requireToken(token, mux))
	return root
}

type server struct {
	m      *sandboxd.Manager
	driver string
	log    *slog.Logger
}

func requireToken(token string, next http.Handler) http.Handler {
	want := []byte(token)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got := []byte(strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer "))
		if len(want) == 0 || subtle.ConstantTimeCompare(got, want) != 1 {
			writeError(w, http.StatusUnauthorized, "a valid token is required")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}

// fail turns an error from the manager into the right status. A bad request or a missing VM is the caller's to see;
// anything else is logged and reported plainly without internals.
func (s *server) fail(w http.ResponseWriter, what string, err error) {
	switch {
	case errors.Is(err, sandboxd.ErrNotFound):
		writeError(w, http.StatusNotFound, "no such VM")
	case errors.Is(err, sandboxd.ErrBusy):
		w.Header().Set("Retry-After", "10")
		writeError(w, http.StatusTooManyRequests, "the host is running its maximum number of VMs; try again shortly")
	case errors.Is(err, sandboxd.ErrBadRequest):
		writeError(w, http.StatusBadRequest, strings.TrimPrefix(err.Error(), sandboxd.ErrBadRequest.Error()+": "))
	default:
		s.log.Error(what, "err", err)
		writeError(w, http.StatusInternalServerError, what+" failed: "+err.Error())
	}
}

func decode(w http.ResponseWriter, r *http.Request, into any) bool {
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<20))
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

func (s *server) healthz(w http.ResponseWriter, r *http.Request) {
	running, max := s.m.Counts()
	status, code := "ok", http.StatusOK
	if err := s.m.Ping(r.Context()); err != nil {
		status, code = "driver down", http.StatusServiceUnavailable
		s.log.Warn("driver not answering", "err", err)
	}
	writeJSON(w, code, map[string]any{"status": status, "driver": s.driver, "vms": running, "max_vms": max})
}

func (s *server) create(w http.ResponseWriter, r *http.Request) {
	var in sandboxd.CreateRequest
	if !decode(w, r, &in) {
		return
	}
	vm, err := s.m.Create(r.Context(), in)
	if err != nil {
		s.fail(w, "create VM", err)
		return
	}
	s.log.Info("vm created", "id", vm.ID, "image", vm.Image)
	writeJSON(w, http.StatusCreated, vm)
}

func (s *server) list(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, s.m.List())
}

func (s *server) destroy(w http.ResponseWriter, r *http.Request) {
	if err := s.m.Destroy(r.Context(), r.PathValue("id")); err != nil {
		s.fail(w, "destroy VM", err)
		return
	}
	s.log.Info("vm destroyed", "id", r.PathValue("id"))
	w.WriteHeader(http.StatusNoContent)
}

// upload takes a tar archive as the body and unpacks it into ?dir= inside the VM.
func (s *server) upload(w http.ResponseWriter, r *http.Request) {
	dir := r.URL.Query().Get("dir")
	if dir == "" {
		dir = "/work"
	}
	if err := s.m.Upload(r.Context(), r.PathValue("id"), dir, r.Body); err != nil {
		s.fail(w, "upload", err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

type execIn struct {
	// Command is run by a shell inside the VM, so pipes and && work.
	Command        string            `json:"command"`
	TimeoutSeconds int               `json:"timeout_seconds"`
	Env            map[string]string `json:"env"`
	WorkDir        string            `json:"workdir"`
	Detach         bool              `json:"detach"`
}

func (s *server) exec(w http.ResponseWriter, r *http.Request) {
	var in execIn
	if !decode(w, r, &in) {
		return
	}
	if strings.TrimSpace(in.Command) == "" {
		writeError(w, http.StatusBadRequest, "command is empty")
		return
	}
	res, err := s.m.Exec(r.Context(), r.PathValue("id"), sandboxd.ExecSpec{
		Command: []string{"sh", "-c", in.Command}, Env: in.Env, WorkDir: in.WorkDir, Detach: in.Detach,
		Timeout: time.Duration(in.TimeoutSeconds) * time.Second,
	})
	if err != nil {
		s.fail(w, "exec", err)
		return
	}
	writeJSON(w, http.StatusOK, res)
}

func (s *server) ports(w http.ResponseWriter, r *http.Request) {
	ports, err := s.m.ListeningPorts(r.Context(), r.PathValue("id"))
	if err != nil {
		s.fail(w, "list ports", err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ports": ports})
}

type requestIn struct {
	Method         string            `json:"method"`
	Port           int               `json:"port"`
	Path           string            `json:"path"`
	Headers        map[string]string `json:"headers"`
	Body           []byte            `json:"body"` // base64 in JSON
	TimeoutSeconds int               `json:"timeout_seconds"`
}

func (s *server) request(w http.ResponseWriter, r *http.Request) {
	var in requestIn
	if !decode(w, r, &in) {
		return
	}
	res, err := s.m.Request(r.Context(), r.PathValue("id"), sandboxd.HTTPRequest{
		Method: in.Method, Port: in.Port, Path: in.Path, Headers: in.Headers, Body: in.Body,
		Timeout: time.Duration(in.TimeoutSeconds) * time.Second,
	})
	if err != nil {
		s.fail(w, "request", err)
		return
	}
	writeJSON(w, http.StatusOK, res)
}
