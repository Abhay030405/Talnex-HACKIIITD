package r2

import (
	"context"
	"io"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"
)

// Runs against the local S3 container. Skipped unless TALNEX_TEST_S3_ENDPOINT is set.
func testStore(t *testing.T) *Store {
	t.Helper()
	endpoint := os.Getenv("TALNEX_TEST_S3_ENDPOINT")
	if endpoint == "" {
		t.Skip("TALNEX_TEST_S3_ENDPOINT is not set")
	}
	s, err := New(Options{
		Endpoint: endpoint, Region: "auto", Bucket: "talnex-test",
		AccessKey: os.Getenv("TALNEX_TEST_S3_ACCESS_KEY"), SecretKey: os.Getenv("TALNEX_TEST_S3_SECRET_KEY"),
		ViewLinkTTL: time.Minute,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := s.EnsureBucket(context.Background()); err != nil {
		t.Fatal(err)
	}
	return s
}

func TestPutGetViewLinkDelete(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	key := ScreenKey("p1", "r1", 1)

	if err := s.Put(ctx, key, strings.NewReader("hello proof"), -1, "text/plain"); err != nil {
		t.Fatal(err)
	}
	rc, err := s.Get(ctx, key)
	if err != nil {
		t.Fatal(err)
	}
	body, _ := io.ReadAll(rc)
	rc.Close()
	if string(body) != "hello proof" {
		t.Fatalf("got %q", body)
	}

	link, err := s.ViewLink(ctx, key)
	if err != nil {
		t.Fatal(err)
	}
	resp, err := http.Get(link)
	if err != nil {
		t.Fatal(err)
	}
	viaLink, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != 200 || string(viaLink) != "hello proof" {
		t.Fatalf("view link gave %d %q", resp.StatusCode, viaLink)
	}

	if err := s.Delete(ctx, key); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Get(ctx, key); err == nil {
		t.Fatal("file should be gone")
	}
}

func TestDeletePrefixRemovesAFolder(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()
	for _, name := range []string{"cv.pdf", "cv2.pdf"} {
		if err := s.Put(ctx, ResumeKey("c9", name), strings.NewReader("x"), -1, "application/pdf"); err != nil {
			t.Fatal(err)
		}
	}
	if err := s.DeletePrefix(ctx, ResumePrefix("c9")); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Get(ctx, ResumeKey("c9", "cv.pdf")); err == nil {
		t.Fatal("resume should be deleted")
	}
}

func TestKeysMatchTheArchitecture(t *testing.T) {
	cases := map[string]string{
		ScreenKey("p", "r", 3):            "screens/p/r/3",
		VideoKey("p", "demo.mp4"):         "videos/p/demo.mp4",
		FrameKey("p", "f1.jpg"):           "frames/p/f1.jpg",
		ResumeKey("c", "cv.pdf"):          "resumes/c/cv.pdf",
		ReplayKey("c", "weekly-1", "B"):   "replays/c/weekly-1/B",
		SandboxKey("p", "r", "build.log"): "sandbox/p/r/build.log",
	}
	for got, want := range cases {
		if got != want {
			t.Errorf("got %s want %s", got, want)
		}
	}
}
