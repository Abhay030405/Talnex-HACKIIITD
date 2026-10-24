package http_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"mime/multipart"
	nethttp "net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	apihttp "github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/http"
)

type fakeFiles struct{ saved map[string][]byte }

func (f *fakeFiles) Put(_ context.Context, key string, r io.Reader, _ int64, _ string) error {
	b, _ := io.ReadAll(r)
	f.saved[key] = b
	return nil
}

func setupResume(t *testing.T) (*httptest.Server, *fakeFiles) {
	t.Helper()
	files := &fakeFiles{saved: map[string][]byte{}}
	h := apihttp.NewHandler(apihttp.Options{
		Pool: dbtest.Pool(t), AuthSecret: secret, WebOrigin: "http://localhost:3000",
		Files: files, Log: slog.New(slog.NewTextHandler(io.Discard, nil)),
	})
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return srv, files
}

func upload(t *testing.T, base, email, id, field string, data []byte) (*nethttp.Response, []byte) {
	t.Helper()
	var body bytes.Buffer
	mw := multipart.NewWriter(&body)
	part, _ := mw.CreateFormFile(field, "cv.pdf")
	_, _ = part.Write(data)
	_ = mw.Close()
	req, _ := nethttp.NewRequest("POST", base+"/v1/candidates/"+id+"/resume", &body)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	if email != "" {
		tok, _ := auth.Sign(secret, email, "", time.Minute)
		req.Header.Set("Authorization", "Bearer "+tok)
	}
	resp, err := nethttp.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	return resp, out
}

func makeCandidate(t *testing.T, base, email string) string {
	t.Helper()
	resp, out := call(t, "POST", base+"/v1/candidates", email, map[string]any{"label": "Asha"})
	if resp.StatusCode != 201 {
		t.Fatalf("create candidate: %d %s", resp.StatusCode, out)
	}
	var c struct {
		ID string `json:"id"`
	}
	_ = json.Unmarshal(out, &c)
	return c.ID
}

func TestResumeUploadSavesTheFileAndStartsReading(t *testing.T) {
	srv, files := setupResume(t)
	id := makeCandidate(t, srv.URL, "cv1@example.com")
	pdf := []byte("%PDF-1.4 pretend resume")

	resp, out := upload(t, srv.URL, "cv1@example.com", id, "resume", pdf)
	if resp.StatusCode != 202 {
		t.Fatalf("upload: %d %s", resp.StatusCode, out)
	}
	if !bytes.Equal(files.saved["resumes/"+id+"/resume.pdf"], pdf) {
		t.Errorf("file not saved under the resume key: %v", files.saved)
	}
	// The first read is still waiting, so a second upload must not start a second read.
	if resp, _ := upload(t, srv.URL, "cv1@example.com", id, "resume", pdf); resp.StatusCode != 409 {
		t.Errorf("second upload while reading: %d, want 409", resp.StatusCode)
	}
}

func TestResumeUploadRules(t *testing.T) {
	srv, files := setupResume(t)
	id := makeCandidate(t, srv.URL, "cv2@example.com")

	if resp, _ := upload(t, srv.URL, "cv3@example.com", id, "resume", []byte("%PDF-1.4")); resp.StatusCode != 404 {
		t.Errorf("a stranger got %d, want 404", resp.StatusCode)
	}
	if resp, _ := upload(t, srv.URL, "cv2@example.com", id, "resume", []byte("not a pdf at all")); resp.StatusCode != 400 {
		t.Errorf("a text file got %d, want 400", resp.StatusCode)
	}
	if resp, _ := upload(t, srv.URL, "cv2@example.com", id, "wrongname", []byte("%PDF-1.4")); resp.StatusCode != 400 {
		t.Errorf("wrong field name got %d, want 400", resp.StatusCode)
	}
	big := append([]byte("%PDF-"), make([]byte, 6<<20)...)
	if resp, _ := upload(t, srv.URL, "cv2@example.com", id, "resume", big); resp.StatusCode != 413 {
		t.Errorf("a file over 5 MB got %d, want 413", resp.StatusCode)
	}
	if len(files.saved) != 0 {
		t.Errorf("a refused upload was saved: %v", files.saved)
	}
	if resp, _ := upload(t, srv.URL, "", id, "resume", []byte("%PDF-1.4")); resp.StatusCode != 401 {
		t.Errorf("no sign-in got %d, want 401", resp.StatusCode)
	}
}
