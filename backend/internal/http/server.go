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
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/live"
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
	// SMSGatewayKey is the secret the team phone sends in X-Gateway-Key. Empty switches phone sign-up off.
	SMSGatewayKey string
	// Ready reports whether the services behind the API are reachable (database, storage).
	Ready func(ctx context.Context) error
	// Walkthrough limits the voice walkthrough questions (recording size, questions per day).
	Walkthrough WalkthroughLimits
	// Tour limits the guided tours (tours per project per day).
	Tour TourLimits
	// Live passes the worker's live events to viewers (docs/live_events.md). Nil turns the live view off.
	Live *live.Hub
}

type server struct {
	opts       Options
	events     *events.Store
	candidates *candidates.Store
	projects   *projects.Store
	queue      *jobs.Queue
	sms        *smsLimiter
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
		sms:        &smsLimiter{},
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
	private.HandleFunc("POST /v1/roles", auth.RequireRole(auth.RoleRecruiter, s.createRole))
	private.HandleFunc("GET /v1/roles", auth.RequireRole(auth.RoleRecruiter, s.listRoles))
	private.HandleFunc("GET /v1/roles/{id}", auth.RequireRole(auth.RoleRecruiter, s.getRole))
	private.HandleFunc("POST /v1/candidates", auth.RequireRole(auth.RoleRecruiter, s.createCandidate))
	private.HandleFunc("GET /v1/candidates", auth.RequireRole(auth.RoleRecruiter, s.listCandidates))
	private.HandleFunc("GET /v1/candidates/{id}", auth.RequireRole(auth.RoleRecruiter, s.getCandidate))
	private.HandleFunc("POST /v1/candidates/{id}/resume", auth.RequireRole(auth.RoleRecruiter, s.uploadResume))
	private.HandleFunc("GET /v1/candidates/{id}/report", auth.RequireRole(auth.RoleRecruiter, s.getReport))
	private.HandleFunc("GET /v1/candidates/{id}/progress", auth.RequireRole(auth.RoleRecruiter, s.getProgress))
	private.HandleFunc("GET /v1/candidates/{id}/found", auth.RequireRole(auth.RoleRecruiter, s.getFound))
	private.HandleFunc("POST /v1/candidates/{id}/confirm", auth.RequireRole(auth.RoleRecruiter, s.confirmCandidate))
	private.HandleFunc("DELETE /v1/candidates/{id}", auth.RequireRole(auth.RoleRecruiter, s.deleteCandidate))
	private.HandleFunc("POST /v1/projects/{id}/walkthroughs", auth.RequireRole(auth.RoleOrganizer, s.askProjectWalkthrough))
	private.HandleFunc("GET /v1/projects/{id}/walkthroughs", auth.RequireRole(auth.RoleOrganizer, s.listProjectWalkthroughs))
	private.HandleFunc("POST /v1/candidate-projects/{id}/walkthroughs", auth.RequireRole(auth.RoleRecruiter, s.askCandidateProjectWalkthrough))
	private.HandleFunc("GET /v1/candidate-projects/{id}/walkthroughs", auth.RequireRole(auth.RoleRecruiter, s.listCandidateProjectWalkthroughs))
	// Either kind of account; only the person who asked sees the answer.
	private.HandleFunc("GET /v1/walkthroughs/{id}", s.getWalkthrough)
	// Guided tour (architecture section 32): a chat beside the live site. Either kind of account; only the owner sees it.
	private.HandleFunc("POST /v1/projects/{id}/tours", auth.RequireRole(auth.RoleOrganizer, s.startProjectTour))
	private.HandleFunc("POST /v1/candidate-projects/{id}/tours", auth.RequireRole(auth.RoleRecruiter, s.startCandidateProjectTour))
	private.HandleFunc("POST /v1/tours/{id}/messages", s.askTour)
	private.HandleFunc("GET /v1/tours/{id}", s.getTour)
	// Live view: what TalNex is doing right now on a project, a resume project, a candidate or a whole event.
	private.HandleFunc("GET /v1/live/{kind}/{id}", s.getLive)
	if o.EnableDevEndpoints {
		private.HandleFunc("POST /v1/dev/selftest", s.startSelfTest)
		private.HandleFunc("GET /v1/dev/selftest/{target}", s.selfTestStatus)
	}

	root := http.NewServeMux()
	root.Handle("/healthz", public)
	root.Handle("/readyz", public)
	// Gateway route: the phone has no user, so it skips sign-in and is checked by its gateway key instead.
	root.HandleFunc("POST /v1/sms/incoming", s.incomingSMS)
	if o.EnableDevEndpoints {
		// Local demos only: mission control for everything the worker is doing, with no sign-in.
		root.HandleFunc("GET /v1/dev/live", s.getDevLive)
		root.HandleFunc("GET /v1/dev/live/view", s.getDevLiveView)
		root.HandleFunc("GET /v1/dev/live/names", s.getDevLiveNames)
	}
	root.Handle("/", auth.Middleware(o.Pool, o.AuthSecret)(private))

	return recoverer(o.Log)(logger(o.Log)(cors(o.WebOrigin)(root)))
}
