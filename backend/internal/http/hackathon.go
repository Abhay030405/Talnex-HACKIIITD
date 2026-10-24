package http

import (
	"net/http"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/projects"
)

// Hackathon routes: projects inside an event, and starting or re-running their checks.
// Every handler checks that the signed-in organizer owns the event or project first, and a
// thing that is missing or owned by someone else gets the same "not found".

func (s *server) ownedEvent(w http.ResponseWriter, r *http.Request) (auth.Identity, string, bool) {
	who, ok := s.identity(w, r)
	if !ok {
		return who, "", false
	}
	id := r.PathValue("id")
	owns, err := auth.OwnsEvent(r.Context(), s.opts.Pool, who.UserID, id)
	if err != nil {
		s.fail(w, "check event owner", err)
		return who, "", false
	}
	if !owns {
		writeError(w, http.StatusNotFound, "event not found")
		return who, "", false
	}
	return who, id, true
}

func (s *server) ownedProject(w http.ResponseWriter, r *http.Request) (string, bool) {
	who, ok := s.identity(w, r)
	if !ok {
		return "", false
	}
	id := r.PathValue("id")
	owns, err := auth.OwnsProject(r.Context(), s.opts.Pool, who.UserID, id)
	if err != nil {
		s.fail(w, "check project owner", err)
		return "", false
	}
	if !owns {
		writeError(w, http.StatusNotFound, "project not found")
		return "", false
	}
	return id, true
}

func (s *server) createProject(w http.ResponseWriter, r *http.Request) {
	_, eventID, ok := s.ownedEvent(w, r)
	if !ok {
		return
	}
	var in projects.NewProject
	if !decode(w, r, &in) {
		return
	}
	if err := in.Validate(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	p, err := s.projects.Create(r.Context(), eventID, in)
	if err != nil {
		s.fail(w, "create project", err)
		return
	}
	writeJSON(w, http.StatusCreated, p)
}

func (s *server) listProjects(w http.ResponseWriter, r *http.Request) {
	_, eventID, ok := s.ownedEvent(w, r)
	if !ok {
		return
	}
	list, err := s.projects.ListForEvent(r.Context(), eventID)
	if err != nil {
		s.fail(w, "list projects", err)
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func (s *server) getProject(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedProject(w, r)
	if !ok {
		return
	}
	p, err := s.projects.Get(r.Context(), id)
	if err != nil {
		s.fail(w, "get project", err)
		return
	}
	writeJSON(w, http.StatusOK, p)
}

// runProject starts a check of one project, or a re-run of it. A check that is still going is
// never started twice.
func (s *server) runProject(w http.ResponseWriter, r *http.Request) {
	id, ok := s.ownedProject(w, r)
	if !ok {
		return
	}
	run, started, err := s.startCheck(r, id)
	if err != nil {
		s.fail(w, "start project check", err)
		return
	}
	if !started {
		writeError(w, http.StatusConflict, "this project is still being checked")
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"project_id": id, "run": run})
}

// runEvent starts the first check of every project in the event that has not been checked yet.
// Projects already checked or being checked are left alone; use the project's own re-run for those.
func (s *server) runEvent(w http.ResponseWriter, r *http.Request) {
	_, eventID, ok := s.ownedEvent(w, r)
	if !ok {
		return
	}
	list, err := s.projects.ListForEvent(r.Context(), eventID)
	if err != nil {
		s.fail(w, "list projects", err)
		return
	}
	started, skipped := []string{}, []string{}
	for _, p := range list {
		run, _, err := s.projects.NextRun(r.Context(), pipeline.Hackathon, p.ID)
		if err != nil {
			s.fail(w, "find next run", err)
			return
		}
		if run != 1 {
			skipped = append(skipped, p.ID)
			continue
		}
		if _, ok, err := s.startCheckRun(r, p.ID, 1); err != nil {
			s.fail(w, "start project check", err)
			return
		} else if ok {
			started = append(started, p.ID)
		}
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"started": started, "skipped": skipped})
}

// startCheck starts the next run of the hackathon pipeline for a project.
func (s *server) startCheck(r *http.Request, projectID string) (run int, started bool, err error) {
	run, active, err := s.projects.NextRun(r.Context(), pipeline.Hackathon, projectID)
	if err != nil || active {
		return run, false, err
	}
	return s.startCheckRun(r, projectID, run)
}

func (s *server) startCheckRun(r *http.Request, projectID string, run int) (int, bool, error) {
	ids, err := s.queue.StartPipeline(r.Context(), pipeline.Hackathon, "project", projectID, run)
	if err != nil {
		return run, false, err
	}
	return run, len(ids) > 0, nil
}
