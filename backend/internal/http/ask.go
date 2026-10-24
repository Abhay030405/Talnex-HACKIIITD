package http

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
)

const maxAskChars = 1000

// askCandidate queues one question about the candidate's report for the Python worker (job report_answer).
func (s *server) askCandidate(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedCandidate(w, r); ok {
		s.ask(w, r, "candidate", id)
	}
}

// askProject is Ask TalNex for a hackathon project, answered from its proof card.
func (s *server) askProject(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedProject(w, r); ok {
		s.ask(w, r, "project", id)
	}
}

func (s *server) listCandidateAsks(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedCandidate(w, r); ok {
		s.listAsks(w, r, id)
	}
}

func (s *server) listProjectAsks(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedProject(w, r); ok {
		s.listAsks(w, r, id)
	}
}

func (s *server) ask(w http.ResponseWriter, r *http.Request, targetType, id string) {
	var in struct {
		Question string `json:"question"`
	}
	if !decode(w, r, &in) {
		return
	}
	q := strings.TrimSpace(in.Question)
	if q == "" || len([]rune(q)) > maxAskChars {
		writeError(w, http.StatusBadRequest, "ask a question of up to 1000 characters")
		return
	}
	var run int
	if err := s.opts.Pool.QueryRow(r.Context(),
		`SELECT coalesce(max(run_number), 0) + 1 FROM jobs WHERE job_type = 'report_answer' AND target_id = $1::uuid`, id).Scan(&run); err != nil {
		s.fail(w, "count questions", err)
		return
	}
	jobID, err := s.queue.Enqueue(r.Context(), jobs.EnqueueParams{
		Type: "report_answer", Runner: "python", TargetType: targetType, TargetID: id,
		Input: map[string]any{"question": q}, RunNumber: run, TimeLimit: 3 * time.Minute, MaxTries: 2,
	})
	if err != nil {
		s.fail(w, "ask", err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"id": jobID})
}

// listAsks returns the questions asked about a candidate or project, newest first, with their answers when ready.
func (s *server) listAsks(w http.ResponseWriter, r *http.Request, id string) {
	rows, err := s.opts.Pool.Query(r.Context(), `
		SELECT id::text, input->>'question', status, coalesce(result, '{}'::jsonb), created_at
		  FROM jobs WHERE job_type = 'report_answer' AND target_id = $1::uuid ORDER BY created_at DESC LIMIT 30`, id)
	if err != nil {
		s.fail(w, "list questions", err)
		return
	}
	defer rows.Close()
	type ask struct {
		ID       string          `json:"id"`
		Question string          `json:"question"`
		Status   string          `json:"status"`
		Result   json.RawMessage `json:"result"`
		Asked    time.Time       `json:"asked_at"`
	}
	out := []ask{}
	for rows.Next() {
		var a ask
		if err := rows.Scan(&a.ID, &a.Question, &a.Status, &a.Result, &a.Asked); err != nil {
			s.fail(w, "read question", err)
			return
		}
		out = append(out, a)
	}
	writeJSON(w, http.StatusOK, out)
}
