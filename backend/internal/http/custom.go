package http

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
)

const maxInstructionChars = 500

// Custom tests (Ask TalNex): one test the reviewer described in their own words, run on the project's live site.
// The result lives only on the job, so it never changes a score.

func (s *server) customTestCandidateProject(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedCandidateProject(w, r); ok {
		s.startCustomTest(w, r, "candidate_project", id)
	}
}

func (s *server) customTestProject(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedProject(w, r); ok {
		s.startCustomTest(w, r, "project", id)
	}
}

func (s *server) listCandidateProjectCustomTests(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedCandidateProject(w, r); ok {
		s.listCustomTests(w, r, id)
	}
}

func (s *server) listProjectCustomTests(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedProject(w, r); ok {
		s.listCustomTests(w, r, id)
	}
}

func (s *server) startCustomTest(w http.ResponseWriter, r *http.Request, targetType, id string) {
	var in struct {
		Instruction string `json:"instruction"`
	}
	if !decode(w, r, &in) {
		return
	}
	text := strings.TrimSpace(in.Instruction)
	if text == "" || len([]rune(text)) > maxInstructionChars {
		writeError(w, http.StatusBadRequest, "describe the test in up to 500 characters")
		return
	}
	var run int
	if err := s.opts.Pool.QueryRow(r.Context(),
		`SELECT coalesce(max(run_number), 0) + 1 FROM jobs WHERE job_type = 'custom_test' AND target_id = $1::uuid`, id).Scan(&run); err != nil {
		s.fail(w, "count custom tests", err)
		return
	}
	jobID, err := s.queue.Enqueue(r.Context(), jobs.EnqueueParams{
		Type: "custom_test", Runner: "python", TargetType: targetType, TargetID: id,
		Input: map[string]any{"instruction": text}, RunNumber: run, TimeLimit: 15 * time.Minute, MaxTries: 1,
	})
	if err != nil {
		s.fail(w, "start custom test", err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"id": jobID})
}

// listCustomTests returns the custom tests of one project, newest first; screenshot keys become short-lived links.
func (s *server) listCustomTests(w http.ResponseWriter, r *http.Request, id string) {
	rows, err := s.opts.Pool.Query(r.Context(), `
		SELECT id::text, input->>'instruction', status, coalesce(result, '{}'::jsonb), created_at
		  FROM jobs WHERE job_type = 'custom_test' AND target_id = $1::uuid ORDER BY created_at DESC LIMIT 20`, id)
	if err != nil {
		s.fail(w, "list custom tests", err)
		return
	}
	defer rows.Close()
	type test struct {
		ID          string         `json:"id"`
		Instruction string         `json:"instruction"`
		Status      string         `json:"status"`
		Result      map[string]any `json:"result"`
		Asked       time.Time      `json:"asked_at"`
	}
	out := []test{}
	for rows.Next() {
		var (
			t   test
			raw []byte
		)
		if err := rows.Scan(&t.ID, &t.Instruction, &t.Status, &raw, &t.Asked); err != nil {
			s.fail(w, "read custom test", err)
			return
		}
		_ = json.Unmarshal(raw, &t.Result)
		steps, _ := t.Result["steps"].([]any)
		for _, st := range steps {
			step, ok := st.(map[string]any)
			if !ok {
				continue
			}
			key, _ := step["proof_key"].(string)
			delete(step, "proof_key") // storage keys never reach the browser
			if key != "" && s.opts.ProofLinks != nil {
				if link, err := s.opts.ProofLinks.ViewLink(r.Context(), key); err == nil {
					step["proof_url"] = link
				}
			}
		}
		out = append(out, t)
	}
	writeJSON(w, http.StatusOK, out)
}
