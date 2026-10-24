package http

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/storage/r2"
)

// Voice walkthrough routes (architecture section 31): the owner asks about a feature, typed or recorded, and the
// Python worker answers from the evidence. Go only checks the owner, keeps the question, stores the recording and adds
// the `walkthrough_answer` job; it never reads the answer's content except to swap screenshot keys for view links.

// JobWalkthroughAnswer is the Python job that answers one question.
const JobWalkthroughAnswer = "walkthrough_answer"

const (
	// maxQuestionChars is the longest typed question we keep.
	maxQuestionChars = 2000
	// walkthroughListSize is how many questions a list shows, newest first.
	walkthroughListSize = 50
)

// WalkthroughLimits come from the settings (WALKTHROUGH_*). AudioMaxBytes 0 switches recorded questions off;
// QuestionsPerDay 0 means no daily limit.
type WalkthroughLimits struct {
	AudioMaxBytes   int
	QuestionsPerDay int
}

// walkSubject is the project or resume project a question is about.
type walkSubject struct {
	kind   string // project or candidate_project (also the job's target type)
	column string // its column in walkthroughs
	id     string
}

func (s *server) ownedCandidateProject(w http.ResponseWriter, r *http.Request) (string, bool) {
	who, ok := s.identity(w, r)
	if !ok {
		return "", false
	}
	id := r.PathValue("id")
	owns, err := auth.OwnsCandidateProject(r.Context(), s.opts.Pool, who.UserID, id)
	if err != nil {
		s.fail(w, "check resume project owner", err)
		return "", false
	}
	if !owns {
		writeError(w, http.StatusNotFound, "project not found")
		return "", false
	}
	return id, true
}

func (s *server) askProjectWalkthrough(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedProject(w, r); ok {
		s.askWalkthrough(w, r, walkSubject{kind: "project", column: "project_id", id: id})
	}
}

func (s *server) askCandidateProjectWalkthrough(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedCandidateProject(w, r); ok {
		s.askWalkthrough(w, r, walkSubject{kind: "candidate_project", column: "candidate_project_id", id: id})
	}
}

func (s *server) listProjectWalkthroughs(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedProject(w, r); ok {
		s.listWalkthroughs(w, r, walkSubject{kind: "project", column: "project_id", id: id})
	}
}

func (s *server) listCandidateProjectWalkthroughs(w http.ResponseWriter, r *http.Request) {
	if id, ok := s.ownedCandidateProject(w, r); ok {
		s.listWalkthroughs(w, r, walkSubject{kind: "candidate_project", column: "candidate_project_id", id: id})
	}
}

// askWalkthrough takes a question as JSON {"question": "..."} or as a recorded file in the form field "audio".
func (s *server) askWalkthrough(w http.ResponseWriter, r *http.Request, sub walkSubject) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	var question string
	var audio []byte
	var audioType string
	mediaType, _, _ := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if mediaType == "multipart/form-data" {
		if audio, audioType, ok = s.readRecording(w, r); !ok {
			return
		}
	} else {
		var in struct {
			Question string `json:"question"`
		}
		if !decode(w, r, &in) {
			return
		}
		question = strings.TrimSpace(in.Question)
		if question == "" {
			writeError(w, http.StatusBadRequest, "question is required")
			return
		}
		if utf8.RuneCountInString(question) > maxQuestionChars {
			writeError(w, http.StatusBadRequest, "the question is too long")
			return
		}
	}

	id := uuid.NewString()
	var audioKey string
	if audio != nil {
		audioKey = r2.VoiceKey(who.UserID, id)
	}
	full, err := s.saveQuestion(r.Context(), sub, who.UserID, id, question, audioKey)
	if err != nil {
		s.fail(w, "save walkthrough question", err)
		return
	}
	if full {
		writeError(w, http.StatusTooManyRequests, "the daily limit of questions for this project is reached; try again tomorrow")
		return
	}
	// The recording is stored before the job exists, so the worker never looks for a file that is not there yet.
	if audio != nil {
		if err := s.opts.Files.Put(r.Context(), audioKey, bytes.NewReader(audio), int64(len(audio)), audioType); err != nil {
			s.markWalkthroughFailed(r.Context(), id, "the recording could not be saved")
			s.fail(w, "save walkthrough recording", err)
			return
		}
	}
	if err := s.enqueueWalkthrough(r.Context(), sub, id); err != nil {
		s.markWalkthroughFailed(r.Context(), id, "the question could not be queued")
		s.fail(w, "queue walkthrough", err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"id": id, "status": "queued"})
}

// readRecording reads the "audio" form file. Only real audio is kept (the type is read from the file itself).
func (s *server) readRecording(w http.ResponseWriter, r *http.Request) ([]byte, string, bool) {
	limit := s.opts.Walkthrough.AudioMaxBytes
	if limit <= 0 || s.opts.Files == nil {
		writeError(w, http.StatusServiceUnavailable, "recorded questions are not available; type the question instead")
		return nil, "", false
	}
	tooBig := func() {
		writeError(w, http.StatusRequestEntityTooLarge, "the recording is too long; ask a shorter question")
	}
	r.Body = http.MaxBytesReader(w, r.Body, int64(limit)+(1<<20))
	file, _, err := r.FormFile("audio")
	if err != nil {
		var maxErr *http.MaxBytesError
		if errors.As(err, &maxErr) {
			tooBig()
			return nil, "", false
		}
		writeError(w, http.StatusBadRequest, "send the recording as a form file called \"audio\"")
		return nil, "", false
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, int64(limit)+1))
	if err != nil {
		writeError(w, http.StatusBadRequest, "could not read the uploaded file")
		return nil, "", false
	}
	if len(data) > limit {
		tooBig()
		return nil, "", false
	}
	if len(data) == 0 {
		writeError(w, http.StatusBadRequest, "the recording is empty")
		return nil, "", false
	}
	kind := http.DetectContentType(data)
	if !isAudio(kind) {
		writeError(w, http.StatusBadRequest, "the recording must be an audio file")
		return nil, "", false
	}
	return data, kind, true
}

// isAudio accepts what browsers record (WebM, Ogg, MP4/M4A) and common audio files (WAV, MP3).
func isAudio(kind string) bool {
	kind, _, _ = strings.Cut(kind, ";")
	return strings.HasPrefix(kind, "audio/") || kind == "video/webm" || kind == "application/ogg" || kind == "video/mp4"
}

// saveQuestion keeps the question unless the subject already reached its daily limit (full = true). The lock makes
// two questions sent at the same moment count one after the other.
func (s *server) saveQuestion(ctx context.Context, sub walkSubject, owner, id, question, audioKey string) (full bool, err error) {
	tx, err := s.opts.Pool.Begin(ctx)
	if err != nil {
		return false, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('walkthrough:' || $1))`, sub.id); err != nil {
		return false, err
	}
	if limit := s.opts.Walkthrough.QuestionsPerDay; limit > 0 {
		var asked int
		if err := tx.QueryRow(ctx, `SELECT count(*) FROM walkthroughs WHERE `+sub.column+` = $1::uuid
		                              AND created_at > now() - interval '1 day'`, sub.id).Scan(&asked); err != nil {
			return false, err
		}
		if asked >= limit {
			return true, nil
		}
	}
	if _, err := tx.Exec(ctx, `INSERT INTO walkthroughs (id, owner_id, `+sub.column+`, question, audio_key)
		VALUES ($1::uuid, $2::uuid, $3::uuid, NULLIF($4, ''), NULLIF($5, ''))`, id, owner, sub.id, question, audioKey); err != nil {
		return false, err
	}
	return false, tx.Commit(ctx)
}

// enqueueWalkthrough adds the answer job. Each question gets the next run number of its subject, so the queue's
// "same job twice" check never merges two questions.
func (s *server) enqueueWalkthrough(ctx context.Context, sub walkSubject, id string) error {
	input, _ := json.Marshal(map[string]string{"walkthrough_id": id})
	tx, err := s.opts.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('walkthrough_job:' || $1))`, sub.id); err != nil {
		return err
	}
	var jobID *string
	err = tx.QueryRow(ctx, `
		SELECT enqueue_job($1, 'python', $2, $3::uuid, $4::jsonb, NULL,
		       (SELECT coalesce(max(run_number), 0) + 1 FROM jobs WHERE job_type = $1 AND target_id = $3::uuid))::text`,
		JobWalkthroughAnswer, sub.kind, sub.id, string(input)).Scan(&jobID)
	if err != nil {
		return err
	}
	if jobID == nil {
		return errors.New("the walkthrough job was not added")
	}
	return tx.Commit(ctx)
}

func (s *server) markWalkthroughFailed(ctx context.Context, id, reason string) {
	if _, err := s.opts.Pool.Exec(ctx, `UPDATE walkthroughs SET status = 'failed', error = $2 WHERE id = $1::uuid`, id, reason); err != nil {
		s.opts.Log.Error("mark walkthrough failed", "err", err)
	}
}

const walkthroughColumns = `id::text, status, question, answer, error, created_at, answered_at`

func (s *server) scanWalkthrough(ctx context.Context, row pgx.Row) (map[string]any, error) {
	var id, status string
	var question, errText *string
	var answer []byte
	var created time.Time
	var answered *time.Time
	if err := row.Scan(&id, &status, &question, &answer, &errText, &created, &answered); err != nil {
		return nil, err
	}
	out := map[string]any{"id": id, "status": status, "question": question, "answer": nil, "error": errText,
		"created_at": created.UTC().Format(time.RFC3339), "answered_at": nil}
	if answered != nil {
		out["answered_at"] = answered.UTC().Format(time.RFC3339)
	}
	if len(answer) > 0 {
		var a map[string]any
		if err := json.Unmarshal(answer, &a); err != nil {
			return nil, err
		}
		s.swapScreenshotKeys(ctx, a)
		out["answer"] = a
	}
	return out, nil
}

func (s *server) listWalkthroughs(w http.ResponseWriter, r *http.Request, sub walkSubject) {
	rows, err := s.opts.Pool.Query(r.Context(), `SELECT `+walkthroughColumns+` FROM walkthroughs
		WHERE `+sub.column+` = $1::uuid ORDER BY created_at DESC, id LIMIT $2`, sub.id, walkthroughListSize)
	if err != nil {
		s.fail(w, "list walkthroughs", err)
		return
	}
	defer rows.Close()
	out := []map[string]any{}
	for rows.Next() {
		item, err := s.scanWalkthrough(r.Context(), rows)
		if err != nil {
			s.fail(w, "read walkthroughs", err)
			return
		}
		out = append(out, item)
	}
	if err := rows.Err(); err != nil {
		s.fail(w, "read walkthroughs", err)
		return
	}
	writeJSON(w, http.StatusOK, out)
}

// getWalkthrough returns one question and its answer. Only the person who asked it (the report's owner) sees it;
// anyone else, and a badly formed id, get "not found".
func (s *server) getWalkthrough(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	id := r.PathValue("id")
	if _, err := uuid.Parse(id); err != nil {
		writeError(w, http.StatusNotFound, "question not found")
		return
	}
	item, err := s.scanWalkthrough(r.Context(), s.opts.Pool.QueryRow(r.Context(),
		`SELECT `+walkthroughColumns+` FROM walkthroughs WHERE id = $1::uuid AND owner_id = $2::uuid`, id, who.UserID))
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "question not found")
		return
	}
	if err != nil {
		s.fail(w, "read walkthrough", err)
		return
	}
	writeJSON(w, http.StatusOK, item)
}

// swapScreenshotKeys walks flow[], seen[] and missing[] proof refs and turns each screenshot "key" into a short-lived
// "view_url", like the proof card. The key is always removed, so raw storage keys never leave the server.
func (s *server) swapScreenshotKeys(ctx context.Context, answer map[string]any) {
	for _, part := range []string{"flow", "seen", "missing"} {
		items, _ := answer[part].([]any)
		for _, it := range items {
			item, _ := it.(map[string]any)
			refs, _ := item["proof"].([]any)
			for _, rf := range refs {
				ref, _ := rf.(map[string]any)
				if ref == nil || ref["kind"] != "screenshot" {
					continue
				}
				key, _ := ref["key"].(string)
				delete(ref, "key")
				if key == "" || s.opts.ProofLinks == nil {
					continue
				}
				link, err := s.opts.ProofLinks.ViewLink(ctx, key)
				if err != nil {
					s.opts.Log.Error("make proof link", "err", err)
					continue
				}
				ref["view_url"] = link
			}
		}
	}
}
