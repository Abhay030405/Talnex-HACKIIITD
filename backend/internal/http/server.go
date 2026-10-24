// Package http is the public API the website talks to.
package http

import (
	"context"
	"log/slog"
	"net/http"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/candidates"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/events"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/projects"
)

type Options struct {
	Pool               *pgxpool.Pool
	AuthSecret         string
	WebOrigin          string
	EnableDevEndpoints bool
	Log                *slog.Logger
	// Files keeps uploaded resumes. Nil turns resume upload off.
	Files ResumeFiles
	// ProofLinks makes short-lived screenshot links for the report. Nil leaves the links out.
	ProofLinks ProofLinks
	// FileRemover deletes stored files when a candidate is deleted. Nil skips file deletion.
	FileRemover FileRemover
	// Ready reports whether the services behind the API are reachable (database, storage).
	Ready func(ctx context.Context) error
}

type server struct {
	opts       Options
	events     *events.Store
	candidates *candidates.Store
	projects   *projects.Store
	queue      *jobs.Queue
}

// NewHandler builds the API routes.
func NewHandler(o Options) http.Handler {
	if o.Log == nil {
		o.Log = slog.Default()
	}
	s := &server{
		opts:       o,
		events:     events.NewStore(o.Pool),
		candidates: candidates.NewStore(o.Pool),
		projects:   projects.NewStore(o.Pool),
		queue:      jobs.NewQueue(o.Pool),
	}

	public := http.NewServeMux()
	public.HandleFunc("GET /healthz", s.healthz)
	public.HandleFunc("GET /readyz", s.readyz)

	private := http.NewServeMux()
	private.HandleFunc("GET /v1/me", s.me)
	private.HandleFunc("POST /v1/events", auth.RequireRole(auth.RoleOrganizer, s.createEvent))
	private.HandleFunc("GET /v1/events", auth.RequireRole(auth.RoleOrganizer, s.listEvents))
	private.HandleFunc("GET /v1/events/{id}", auth.RequireRole(auth.RoleOrganizer, s.getEvent))
	private.HandleFunc("POST /v1/events/{id}/projects", auth.RequireRole(auth.RoleOrganizer, s.createProject))
	private.HandleFunc("GET /v1/events/{id}/projects", auth.RequireRole(auth.RoleOrganizer, s.listProjects))
	private.HandleFunc("POST /v1/events/{id}/run", auth.RequireRole(auth.RoleOrganizer, s.runEvent))
	private.HandleFunc("GET /v1/projects/{id}", auth.RequireRole(auth.RoleOrganizer, s.getProject))
	private.HandleFunc("GET /v1/projects/{id}/proof", auth.RequireRole(auth.RoleOrganizer, s.getProjectProof))
	private.HandleFunc("GET /v1/events/{id}/overview", auth.RequireRole(auth.RoleOrganizer, s.getEventOverview))
	private.HandleFunc("GET /v1/events/{id}/compare", auth.RequireRole(auth.RoleOrganizer, s.getEventCompare))
	private.HandleFunc("POST /v1/projects/{id}/run", auth.RequireRole(auth.RoleOrganizer, s.runProject))
	private.HandleFunc("POST /v1/candidates", auth.RequireRole(auth.RoleRecruiter, s.createCandidate))
	private.HandleFunc("GET /v1/candidates", auth.RequireRole(auth.RoleRecruiter, s.listCandidates))
	private.HandleFunc("GET /v1/candidates/{id}", auth.RequireRole(auth.RoleRecruiter, s.getCandidate))
	private.HandleFunc("POST /v1/candidates/{id}/resume", auth.RequireRole(auth.RoleRecruiter, s.uploadResume))
	private.HandleFunc("GET /v1/candidates/{id}/report", auth.RequireRole(auth.RoleRecruiter, s.getReport))
	private.HandleFunc("GET /v1/candidates/{id}/progress", auth.RequireRole(auth.RoleRecruiter, s.getProgress))
	private.HandleFunc("GET /v1/candidates/{id}/found", auth.RequireRole(auth.RoleRecruiter, s.getFound))
	private.HandleFunc("POST /v1/candidates/{id}/confirm", auth.RequireRole(auth.RoleRecruiter, s.confirmCandidate))
	private.HandleFunc("DELETE /v1/candidates/{id}", auth.RequireRole(auth.RoleRecruiter, s.deleteCandidate))
	if o.EnableDevEndpoints {
		private.HandleFunc("POST /v1/dev/selftest", s.startSelfTest)
		private.HandleFunc("GET /v1/dev/selftest/{target}", s.selfTestStatus)
	}

	root := http.NewServeMux()
	root.Handle("/healthz", public)
	root.Handle("/readyz", public)
	root.Handle("/", auth.Middleware(o.Pool, o.AuthSecret)(private))

	return recoverer(o.Log)(logger(o.Log)(cors(o.WebOrigin)(root)))
}
