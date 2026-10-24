package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// Guided tour routes (architecture section 32): the owner chats beside the live site; the Python worker reads the
// code in a read-only VM and shows the feature in the browser. Go only checks the owner and the daily limit, keeps
// the messages and adds the `tour_message` job. Progress reaches the page over the live stream of the project.

// JobTourMessage is the Python job that answers one tour message.
const JobTourMessage = "tour_message"

// tourJobSeconds is the time limit of one message: reading code, then walking the live site.
const tourJobSeconds = 1500

// TourLimits come from the settings (TOUR_*). PerDay 0 means no daily limit.
type TourLimits struct {
	PerDay int
}

func (s *server) startProjectTour(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedProject(w, r); ok {
		s.startTour(w, r, walkSubject{kind: "project", column: "project_id", id: id})
	}
}

func (s *server) startCandidateProjectTour(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedCandidateProject(w, r); ok {
		s.startTour(w, r, walkSubject{kind: "candidate_project", column: "candidate_project_id", id: id})
	}
}

// readTourQuestion reads {"question": "..."} and checks its length.
func readTourQuestion(w http.ResponseWriter, r *http.Request) (string, bool) {
	var in struct {
		Question string `json:"question"`
	}
	if !decode(w, r, &in) {
		return "", false
	}
	question := strings.TrimSpace(in.Question)
	if question == "" {
		writeError(w, http.StatusBadRequest, "question is required")
		return "", false
	}
	if utf8.RuneCountInString(question) > maxQuestionChars {
		writeError(w, http.StatusBadRequest, "the question is too long")
		return "", false
	}
	return question, true
}

// startTour opens a chat with its first question, unless the project already had its tours for the day.
func (s *server) startTour(w http.ResponseWriter, r *http.Request, sub walkSubject) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	question, ok := readTourQuestion(w, r)
	if !ok {
		return
	}
	ctx := r.Context()
	tx, err := s.opts.Pool.Begin(ctx)
	if err != nil {
		s.fail(w, "start tour", err)
		return
	}
	defer func() { _ = tx.Rollback(ctx) }()
	// The lock makes two tours started at the same moment count one after the other.
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('tour:' || $1))`, sub.id); err != nil {
		s.fail(w, "start tour", err)
		return
	}
	if limit := s.opts.Tour.PerDay; limit > 0 {
		var started int
		if err := tx.QueryRow(ctx, `SELECT count(*) FROM tour_sessions WHERE `+sub.column+` = $1::uuid
		                              AND created_at > now() - interval '1 day'`, sub.id).Scan(&started); err != nil {
			s.fail(w, "count tours", err)
			return
		}
		if started >= limit {
			writeError(w, http.StatusTooManyRequests, "the daily limit of tours for this project is reached; try again tomorrow")
			return
		}
	}
	tourID, messageID := uuid.NewString(), uuid.NewString()
	if _, err := tx.Exec(ctx, `INSERT INTO tour_sessions (id, owner_id, `+sub.column+`) VALUES ($1::uuid, $2::uuid, $3::uuid)`,
		tourID, who.UserID, sub.id); err != nil {
		s.fail(w, "save tour", err)
		return
	}
	if _, err := tx.Exec(ctx, `INSERT INTO tour_messages (id, session_id, question) VALUES ($1::uuid, $2::uuid, $3)`,
		messageID, tourID, question); err != nil {
		s.fail(w, "save tour question", err)
		return
	}
	if err := s.enqueueTour(ctx, tx, sub, messageID); err != nil {
		s.fail(w, "queue tour", err)
		return
	}
	if err := tx.Commit(ctx); err != nil {
		s.fail(w, "save tour", err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"id": tourID, "message_id": messageID, "status": "queued"})
}

// askTour adds a question to an open chat. Only one question is worked on at a time per chat.
func (s *server) askTour(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	tourID := r.PathValue("id")
	sub, found, err := s.ownedTour(r.Context(), who.UserID, tourID)
	if err != nil {
		s.fail(w, "read tour", err)
		return
	}
	if !found {
		writeError(w, http.StatusNotFound, "tour not found")
		return
	}
	question, ok := readTourQuestion(w, r)
	if !ok {
		return
	}
	ctx := r.Context()
	tx, err := s.opts.Pool.Begin(ctx)
	if err != nil {
		s.fail(w, "ask tour", err)
		return
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('tour_chat:' || $1))`, tourID); err != nil {
		s.fail(w, "ask tour", err)
		return
	}
	var busy bool
	if err := tx.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM tour_messages WHERE session_id = $1::uuid
	                                            AND status IN ('queued', 'working'))`, tourID).Scan(&busy); err != nil {
		s.fail(w, "ask tour", err)
		return
	}
	if busy {
		writeError(w, http.StatusConflict, "the guide is still answering the last question")
		return
	}
	messageID := uuid.NewString()
	if _, err := tx.Exec(ctx, `INSERT INTO tour_messages (id, session_id, question) VALUES ($1::uuid, $2::uuid, $3)`,
		messageID, tourID, question); err != nil {
		s.fail(w, "save tour question", err)
		return
	}
	if err := s.enqueueTour(ctx, tx, sub, messageID); err != nil {
		s.fail(w, "queue tour", err)
		return
	}
	if err := tx.Commit(ctx); err != nil {
		s.fail(w, "ask tour", err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"id": tourID, "message_id": messageID, "status": "queued"})
}

// enqueueTour adds the answer job inside the caller's transaction, so a question never exists without its job. One
// attempt only: a second try would open a second browser on a paid account.
func (s *server) enqueueTour(ctx context.Context, tx pgx.Tx, sub walkSubject, messageID string) error {
	input, _ := json.Marshal(map[string]string{"message_id": messageID})
	var jobID *string
	err := tx.QueryRow(ctx, `
		SELECT enqueue_job($1, 'python', $2, $3::uuid, $4::jsonb, NULL,
		       (SELECT coalesce(max(run_number), 0) + 1 FROM jobs WHERE job_type = $1 AND target_id = $3::uuid),
		       $5, 1)::text`,
		JobTourMessage, sub.kind, sub.id, string(input), tourJobSeconds).Scan(&jobID)
	if err != nil {
		return err
	}
	if jobID == nil {
		return errors.New("the tour job was not added")
	}
	return nil
}

// ownedTour finds a chat the person owns and the project it is about.
func (s *server) ownedTour(ctx context.Context, userID, tourID string) (walkSubject, bool, error) {
	if _, err := uuid.Parse(tourID); err != nil {
		return walkSubject{}, false, nil
	}
	var project, candidate *string
	err := s.opts.Pool.QueryRow(ctx, `SELECT project_id::text, candidate_project_id::text FROM tour_sessions
	                                   WHERE id = $1::uuid AND owner_id = $2::uuid`, tourID, userID).Scan(&project, &candidate)
	if errors.Is(err, pgx.ErrNoRows) {
		return walkSubject{}, false, nil
	}
	if err != nil {
		return walkSubject{}, false, err
	}
	if project != nil {
		return walkSubject{kind: "project", column: "project_id", id: *project}, true, nil
	}
	return walkSubject{kind: "candidate_project", column: "candidate_project_id", id: *candidate}, true, nil
}

// getTour returns a chat with all its questions and replies. The owner only; anyone else gets "not found".
func (s *server) getTour(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	tourID := r.PathValue("id")
	sub, found, err := s.ownedTour(r.Context(), who.UserID, tourID)
	if err != nil {
		s.fail(w, "read tour", err)
		return
	}
	if !found {
		writeError(w, http.StatusNotFound, "tour not found")
		return
	}
	rows, err := s.opts.Pool.Query(r.Context(), `SELECT id::text, question, status, answer, error, created_at, answered_at
	                                              FROM tour_messages WHERE session_id = $1::uuid ORDER BY created_at, id`, tourID)
	if err != nil {
		s.fail(w, "read tour messages", err)
		return
	}
	defer rows.Close()
	messages := []map[string]any{}
	for rows.Next() {
		var id, question, status string
		var answer []byte
		var errText *string
		var created time.Time
		var answered *time.Time
		if err := rows.Scan(&id, &question, &status, &answer, &errText, &created, &answered); err != nil {
			s.fail(w, "read tour messages", err)
			return
		}
		item := map[string]any{"id": id, "question": question, "status": status, "answer": nil, "error": errText,
			"created_at": created.UTC().Format(time.RFC3339), "answered_at": nil}
		if answered != nil {
			item["answered_at"] = answered.UTC().Format(time.RFC3339)
		}
		if len(answer) > 0 {
			var a map[string]any
			if err := json.Unmarshal(answer, &a); err != nil {
				s.fail(w, "read tour answer", err)
				return
			}
			s.swapAnswerKeys(r.Context(), a, "say")
			item["answer"] = a
		}
		messages = append(messages, item)
	}
	if err := rows.Err(); err != nil {
		s.fail(w, "read tour messages", err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"id": tourID, "subject": map[string]string{"kind": sub.kind, "id": sub.id},
		"messages": messages})
}
