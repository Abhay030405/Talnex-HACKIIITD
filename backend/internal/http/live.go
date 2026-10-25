package http

import (
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"net/http"
	"slices"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/live"
)

// livePing keeps proxies from closing a quiet stream.
const livePing = 15 * time.Second

// liveReplay is how many saved events a viewer gets first, so opening the view late still shows what happened.
const liveReplay = 400

//go:embed live_view.html
var liveViewPage []byte

// liveSubjects are the subject ids one stream shows: the target itself, plus its projects for an event or a candidate.
var liveSubjects = map[string]struct {
	owns     func(ctx context.Context, s *server, userID, id string) (bool, error)
	children string // the query for the subjects inside it, or empty
}{
	"project": {owns: func(ctx context.Context, s *server, u, id string) (bool, error) {
		return auth.OwnsProject(ctx, s.opts.Pool, u, id)
	}},
	"candidate_project": {owns: func(ctx context.Context, s *server, u, id string) (bool, error) {
		return auth.OwnsCandidateProject(ctx, s.opts.Pool, u, id)
	}},
	"candidate": {owns: func(ctx context.Context, s *server, u, id string) (bool, error) {
		return auth.OwnsCandidate(ctx, s.opts.Pool, u, id)
	}, children: `SELECT id::text FROM candidate_projects WHERE candidate_id = $1::uuid`},
	"event": {owns: func(ctx context.Context, s *server, u, id string) (bool, error) {
		return auth.OwnsEvent(ctx, s.opts.Pool, u, id)
	}, children: `SELECT id::text FROM projects WHERE event_id = $1::uuid`},
}

// getLive streams what TalNex is doing on one subject, as Server-Sent Events (docs/live_events.md). The owner only.
// For an event it streams every project of the event; for a candidate, every project on the resume.
func (s *server) getLive(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	kind, id := r.PathValue("kind"), r.PathValue("id")
	target, known := liveSubjects[kind]
	if !known {
		writeError(w, http.StatusNotFound, "unknown kind of subject")
		return
	}
	owns, err := target.owns(r.Context(), s, who.UserID, id)
	if err != nil {
		s.fail(w, "check live owner", err)
		return
	}
	if !owns {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if s.opts.Live == nil {
		writeError(w, http.StatusServiceUnavailable, "the live view is off")
		return
	}
	ids := []string{id}
	if target.children != "" {
		rows, err := s.opts.Pool.Query(r.Context(), target.children, id)
		if err != nil {
			s.fail(w, "read live subjects", err)
			return
		}
		for rows.Next() {
			var child string
			if err := rows.Scan(&child); err == nil {
				ids = append(ids, child)
			}
		}
		rows.Close()
	}
	s.stream(w, r, ids)
}

// getDevLive streams every event of every subject. Local demos only (ENABLE_DEV_ENDPOINTS); never on in production.
func (s *server) getDevLive(w http.ResponseWriter, r *http.Request) {
	if s.opts.Live == nil {
		writeError(w, http.StatusServiceUnavailable, "the live view is off")
		return
	}
	s.stream(w, r, nil)
}

// getDevLiveNames maps subject ids to the names people know them by (team, resume project, candidate, event),
// so mission control can label each project's panel. Local demos only.
func (s *server) getDevLiveNames(w http.ResponseWriter, r *http.Request) {
	rows, err := s.opts.Pool.Query(r.Context(), `
		SELECT id::text, team_name, 'project' FROM projects
		UNION ALL SELECT id::text, name, 'candidate_project' FROM candidate_projects
		UNION ALL SELECT id::text, label, 'candidate' FROM candidates
		UNION ALL SELECT id::text, name, 'event' FROM events`)
	if err != nil {
		s.fail(w, "read live names", err)
		return
	}
	defer rows.Close()
	names := map[string]map[string]string{}
	for rows.Next() {
		var id, name, kind string
		if err := rows.Scan(&id, &name, &kind); err == nil {
			names[id] = map[string]string{"name": name, "kind": kind}
		}
	}
	writeJSON(w, http.StatusOK, names)
}

// getDevLiveView is the mission control page for local demos: it watches /v1/dev/live.
func (s *server) getDevLiveView(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	_, _ = w.Write(liveViewPage)
}

// stream sends the saved events for the subjects first, then the live ones, until the viewer leaves.
// ids nil means every subject.
func (s *server) stream(w http.ResponseWriter, r *http.Request, ids []string) {
	rc := http.NewResponseController(w)
	h := w.Header()
	h.Set("Content-Type", "text/event-stream")
	h.Set("Cache-Control", "no-cache")
	h.Set("Connection", "keep-alive")
	h.Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)

	// Subscribe before reading the saved events, so nothing falls in the gap (a viewer may see an event twice).
	var wants func(string) bool
	if ids != nil {
		wants = func(id string) bool { return slices.Contains(ids, id) }
	}
	sub := s.opts.Live.Subscribe(wants)
	defer s.opts.Live.Unsubscribe(sub)

	ctx := r.Context()
	_, _ = fmt.Fprint(w, "event: replay.start\ndata: {}\n\n") // a reconnecting viewer starts from a clean slate
	for _, raw := range s.savedEvents(ctx, ids) {
		if ev, ok := live.Parse(raw); ok {
			s.sendEvent(ctx, w, ev)
		}
	}
	_, _ = fmt.Fprint(w, "event: replay.done\ndata: {}\n\n")
	_ = rc.Flush()

	ping := time.NewTicker(livePing)
	defer ping.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ping.C:
			if _, err := fmt.Fprint(w, ": ping\n\n"); err != nil {
				return
			}
		case ev, open := <-sub.C:
			if !open {
				return
			}
			s.sendEvent(ctx, w, ev)
		}
		if err := rc.Flush(); err != nil {
			return
		}
	}
}

// savedEvents are the latest saved events for the subjects, oldest first. None when the table is missing.
func (s *server) savedEvents(ctx context.Context, ids []string) [][]byte {
	// The latest events of EACH subject: a shared limit let a busy project push out the candidate's own stages (the
	// coding checks run first). ponytail: 400 per subject, so a big event replays many; page it if that gets slow.
	query := `SELECT payload FROM (SELECT id, payload, row_number() OVER (PARTITION BY subject_id ORDER BY id DESC) AS n
		FROM live_events WHERE subject_id = ANY($1::uuid[])) t WHERE n <= $2 ORDER BY id`
	args := []any{ids, liveReplay}
	if ids == nil {
		query = `SELECT payload FROM (SELECT id, payload FROM live_events ORDER BY id DESC LIMIT $1) t ORDER BY id`
		args = []any{liveReplay}
	}
	rows, err := s.opts.Pool.Query(ctx, query, args...)
	if err != nil {
		s.opts.Log.Warn("read saved live events", "err", err)
		return nil
	}
	defer rows.Close()
	var out [][]byte
	for rows.Next() {
		var raw []byte
		if err := rows.Scan(&raw); err == nil {
			out = append(out, raw)
		}
	}
	return out
}

// sendEvent writes one event, with every storage key turned into a short-lived view link first,
// so the browser never sees a storage key.
func (s *server) sendEvent(ctx context.Context, w http.ResponseWriter, ev live.Event) {
	var msg map[string]any
	if err := json.Unmarshal(ev.Raw, &msg); err != nil {
		return
	}
	if data, ok := msg["data"].(map[string]any); ok {
		s.viewLinkInto(ctx, data, "proof_key", "proof_url")
		if keys, ok := data["proof_keys"].([]any); ok {
			delete(data, "proof_keys")
			urls := []string{}
			for _, k := range keys {
				holder := map[string]any{"k": k}
				s.viewLinkInto(ctx, holder, "k", "u")
				if u, ok := holder["u"].(string); ok {
					urls = append(urls, u)
				}
			}
			data["proof_urls"] = urls
		}
	}
	out, err := json.Marshal(msg)
	if err != nil {
		return
	}
	_, _ = fmt.Fprintf(w, "event: %s\ndata: %s\n\n", ev.Kind, out)
}
