package http_test

import (
	"bufio"
	"context"
	"io"
	"log/slog"
	nethttp "net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/auth"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	apihttp "github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/http"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/live"
)

func setupLive(t *testing.T) (*httptest.Server, *live.Hub) {
	t.Helper()
	pool := dbtest.Pool(t)
	hub := live.NewHub(pool, nil)
	h := apihttp.NewHandler(apihttp.Options{
		Pool: pool, AuthSecret: secret, WebOrigin: "http://localhost:3000", EnableDevEndpoints: true,
		Log: slog.New(slog.NewTextHandler(io.Discard, nil)), Live: hub,
	})
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return srv, hub
}

// openStream starts reading a live stream and hands back each "event:" name as it arrives.
func openStream(t *testing.T, url, email string) (<-chan string, int) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	t.Cleanup(cancel)
	req, _ := nethttp.NewRequestWithContext(ctx, "GET", url, nil)
	if email != "" {
		tok, _ := auth.Sign(secret, email, "", time.Minute)
		req.Header.Set("Authorization", "Bearer "+tok)
	}
	resp, err := nethttp.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	names := make(chan string, 64)
	if resp.StatusCode != 200 {
		resp.Body.Close()
		close(names)
		return names, resp.StatusCode
	}
	go func() {
		defer resp.Body.Close()
		defer close(names)
		sc := bufio.NewScanner(resp.Body)
		for sc.Scan() {
			line := sc.Text()
			if strings.HasPrefix(line, "event: ") {
				names <- strings.TrimPrefix(line, "event: ")
			} else if strings.HasPrefix(line, "data: ") && strings.Contains(line, "proof_key") {
				names <- "LEAKED STORAGE KEY"
			}
		}
	}()
	return names, 200
}

func next(t *testing.T, names <-chan string) string {
	t.Helper()
	select {
	case n := <-names:
		return n
	case <-time.After(5 * time.Second):
		t.Fatal("no event arrived")
		return ""
	}
}

func TestTheOwnerSeesSavedThenLiveEventsAndNeverAStorageKey(t *testing.T) {
	srv, hub := setupLive(t)
	event := makeEvent(t, srv.URL, "live-a@example.com", eventBody())
	project := makeProject(t, srv.URL, "live-a@example.com", event, "ants")
	saved := `{"v":1,"kind":"step.record","subject":{"kind":"project","id":"` + project + `"},"data":{"label":"click Add","proof_key":"screens/p/r/1"}}`
	if _, err := dbtest.Pool(t).Exec(context.Background(),
		`INSERT INTO live_events (subject_kind, subject_id, kind, payload) VALUES ('project', $1::uuid, 'step.record', $2::jsonb)`,
		project, saved); err != nil {
		t.Fatal(err)
	}

	names, status := openStream(t, srv.URL+"/v1/live/event/"+event, "live-a@example.com")
	if status != 200 {
		t.Fatalf("status %d", status)
	}
	for _, want := range []string{"replay.start", "step.record", "replay.done"} {
		if got := next(t, names); got != want {
			t.Fatalf("got %q, want %q", got, want)
		}
	}
	// A live event for this event's project arrives; one for another subject does not.
	hub.Publish([]byte(`{"v":1,"kind":"reason","subject":{"kind":"project","id":"00000000-0000-0000-0000-000000000000"},"data":{}}`))
	hub.Publish([]byte(`{"v":1,"kind":"verdict","subject":{"kind":"project","id":"` + project + `"},"data":{"verdict":"works","proof_keys":["screens/p/r/2"]}}`))
	if got := next(t, names); got != "verdict" {
		t.Fatalf("got %q, want verdict", got)
	}
}

func TestAStrangerCannotWatch(t *testing.T) {
	srv, _ := setupLive(t)
	event := makeEvent(t, srv.URL, "live-b@example.com", eventBody())
	if _, status := openStream(t, srv.URL+"/v1/live/event/"+event, "someone-else@example.com"); status != 404 {
		t.Fatalf("a stranger got %d, want 404", status)
	}
	if _, status := openStream(t, srv.URL+"/v1/live/planet/"+event, "live-b@example.com"); status != 404 {
		t.Fatalf("an unknown kind got %d, want 404", status)
	}
}

func TestTheDevViewIsServed(t *testing.T) {
	srv, _ := setupLive(t)
	resp, body := call(t, "GET", srv.URL+"/v1/dev/live/view", "", nil)
	if resp.StatusCode != 200 || !strings.Contains(string(body), "EventSource(\"/v1/dev/live\")") {
		t.Fatalf("view: %d", resp.StatusCode)
	}
}
