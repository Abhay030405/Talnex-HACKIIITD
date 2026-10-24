package http

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/storage/r2"
)

// maxResumeBytes is the biggest resume file we accept. The Python reader refuses larger ones too.
const maxResumeBytes = 5 << 20

// ResumeFiles is the part of file storage the resume upload needs.
type ResumeFiles interface {
	Put(ctx context.Context, key string, r io.Reader, size int64, contentType string) error
}

// uploadResume takes the resume PDF for a candidate, keeps it, and starts reading it.
// The form field is called "resume". The file must start like a PDF; the reader checks the rest.
func (s *server) uploadResume(w http.ResponseWriter, r *http.Request) {
	who, ok := s.identity(w, r)
	if !ok {
		return
	}
	id := r.PathValue("id")
	owns, err := auth.OwnsCandidate(r.Context(), s.opts.Pool, who.UserID, id)
	if err != nil {
		s.fail(w, "check candidate owner", err)
		return
	}
	if !owns {
		writeError(w, http.StatusNotFound, "candidate not found")
		return
	}
	if s.opts.Files == nil {
		writeError(w, http.StatusServiceUnavailable, "resume upload is not available")
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, maxResumeBytes+(1<<20))
	file, _, err := r.FormFile("resume")
	if err != nil {
		var tooBig *http.MaxBytesError
		if errors.As(err, &tooBig) {
			writeError(w, http.StatusRequestEntityTooLarge, "the resume file is larger than 5 MB")
			return
		}
		writeError(w, http.StatusBadRequest, "send the resume PDF as a form file called \"resume\"")
		return
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, maxResumeBytes+1))
	if err != nil {
		writeError(w, http.StatusBadRequest, "could not read the uploaded file")
		return
	}
	if len(data) > maxResumeBytes {
		writeError(w, http.StatusRequestEntityTooLarge, "the resume file is larger than 5 MB")
		return
	}
	if !bytes.HasPrefix(data, []byte("%PDF-")) {
		writeError(w, http.StatusBadRequest, "the resume must be a PDF file")
		return
	}

	run, active, err := s.candidates.NextRun(r.Context(), pipeline.RecruiterCandidate, id)
	if err != nil {
		s.fail(w, "find next run", err)
		return
	}
	if active {
		writeError(w, http.StatusConflict, "this resume is still being read")
		return
	}
	key := r2.ResumeKey(id, "resume.pdf")
	if err := s.opts.Files.Put(r.Context(), key, bytes.NewReader(data), int64(len(data)), "application/pdf"); err != nil {
		s.fail(w, "save resume", err)
		return
	}
	if err := s.candidates.AttachResume(r.Context(), id, key); err != nil {
		s.fail(w, "attach resume", err)
		return
	}
	if _, err := s.queue.StartPipeline(r.Context(), pipeline.RecruiterCandidate, "candidate", id, run); err != nil {
		s.fail(w, "start resume read", err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"candidate_id": id, "run": run})
}
