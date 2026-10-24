package github

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func historyServer(t *testing.T, calls *int32) *Client {
	t.Helper()
	mux := http.NewServeMux()
	var srvURL string
	write := func(w http.ResponseWriter, body string) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}
	mux.HandleFunc("POST /graphql", func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(calls, 1)
		if r.Header.Get("Authorization") != "Bearer tok" {
			http.Error(w, "no token", http.StatusUnauthorized)
			return
		}
		var q struct {
			Query     string         `json:"query"`
			Variables map[string]any `json:"variables"`
		}
		_ = json.NewDecoder(r.Body).Decode(&q)
		switch {
		case q.Variables["name"] == "gone":
			write(w, `{"data":{"repository":null},"errors":[{"type":"NOT_FOUND","message":"Could not resolve to a Repository"}]}`)
		case q.Variables["name"] == "busy":
			write(w, `{"errors":[{"type":"RATE_LIMITED","message":"API rate limit exceeded"}]}`)
		case strings.Contains(q.Query, "totalCount"):
			write(w, `{"data":{"repository":{"object":{"history":{"totalCount":42}}}}}`)
		case q.Variables["path"] == "missing.py":
			write(w, `{"data":{"repository":{"object":{"blame":null}}},"errors":[{"message":"Could not resolve file for path 'missing.py'"}]}`)
		default:
			write(w, `{"data":{"repository":{"object":{"blame":{"ranges":[
				{"startingLine":1,"endingLine":10,"commit":{"oid":"aaa"}},
				{"startingLine":11,"endingLine":30,"commit":{"oid":"bbb"}}]}}}}}`)
		}
	})
	mux.HandleFunc("GET /repos/o/n/commits", func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(calls, 1)
		if r.URL.Query().Get("page") == "2" {
			write(w, `[{"sha":"ccc","commit":{"message":"first","committer":{"date":"2026-03-01T10:00:00Z"}},"author":null,"parents":[]}]`)
			return
		}
		w.Header().Set("Link", `<`+srvURL+`/repos/o/n/commits?page=2&per_page=2>; rel="next", <`+srvURL+`/repos/o/n/commits?page=2>; rel="last"`)
		write(w, `[{"sha":"aaa","commit":{"message":"Add chat\n\nlong body","committer":{"date":"2026-03-03T10:00:00Z"}},
		            "author":{"login":"asha","type":"User"},"parents":[{"sha":"bbb"}]},
		           {"sha":"bbb","commit":{"message":"Bump deps","committer":{"date":"2026-03-02T10:00:00Z"}},
		            "author":{"login":"dependabot[bot]","type":"Bot"},"parents":[{"sha":"ccc"}]}]`)
	})
	mux.HandleFunc("GET /repos/o/n/commits/aaa", func(w http.ResponseWriter, _ *http.Request) {
		atomic.AddInt32(calls, 1)
		write(w, `{"sha":"aaa","commit":{"message":"Add chat\nmore","committer":{"date":"2026-03-03T10:00:00Z"}},
			"author":{"login":"asha","type":"User"},"parents":[{"sha":"bbb"}],"stats":{"additions":120,"deletions":4},
			"files":[{"filename":"chat.py"},{"filename":"app.py"}]}`)
	})
	mux.HandleFunc("GET /repos/o/n/activity", func(w http.ResponseWriter, _ *http.Request) {
		write(w, `[{"before":"ccc","after":"aaa","timestamp":"2026-03-04T09:00:00Z","activity_type":"push"},
		           {"before":"0000000000000000000000000000000000000000","after":"ccc","timestamp":"2026-03-01T11:00:00Z","activity_type":"branch_creation"},
		           {"before":"aaa","after":"0000000000000000000000000000000000000000","timestamp":"2026-03-05T09:00:00Z","activity_type":"branch_deletion"}]`)
	})
	srv := httptest.NewServer(mux)
	srvURL = srv.URL
	t.Cleanup(srv.Close)
	return NewClient(srv.URL, "tok")
}

func TestBlameReadsRangesAndIsCached(t *testing.T) {
	var calls int32
	c := historyServer(t, &calls)
	ctx := context.Background()
	got, err := c.Blame(ctx, "o", "n", "head1", "chat.py")
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[0] != (BlameRange{Start: 1, End: 10, SHA: "aaa"}) || got[1].SHA != "bbb" {
		t.Fatalf("blame = %+v", got)
	}
	before := atomic.LoadInt32(&calls)
	if _, err := c.Blame(ctx, "o", "n", "head1", "chat.py"); err != nil {
		t.Fatal(err)
	}
	if atomic.LoadInt32(&calls) != before {
		t.Error("a second blame of the same commit and file went to GitHub again")
	}
	if _, err := c.Blame(ctx, "o", "n", "head1", "missing.py"); !errors.Is(err, ErrNotFound) {
		t.Errorf("missing file: %v, want ErrNotFound", err)
	}
	if _, err := c.Blame(ctx, "o", "gone", "head1", "a.py"); !errors.Is(err, ErrNotFound) {
		t.Errorf("missing repo: %v, want ErrNotFound", err)
	}
	if _, err := c.Blame(ctx, "o", "busy", "head1", "a.py"); !errors.Is(err, ErrRateLimited) {
		t.Errorf("rate limit: %v, want ErrRateLimited", err)
	}
	if n, err := c.CommitCount(ctx, "o", "n", "head1"); err != nil || n != 42 {
		t.Errorf("commit count = %d, %v", n, err)
	}
}

func TestFileCommitsFollowPagesAndSpotBots(t *testing.T) {
	var calls int32
	c := historyServer(t, &calls)
	got, err := c.FileCommits(context.Background(), "o", "n", "head2", "chat.py", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 3 {
		t.Fatalf("want 3 commits over two pages, got %+v", got)
	}
	if got[0].Message != "Add chat" || got[0].AuthorLogin != "asha" || got[0].IsBot || got[0].Parents != 1 {
		t.Errorf("first commit = %+v", got[0])
	}
	if !got[1].IsBot {
		t.Errorf("dependabot should be a bot: %+v", got[1])
	}
	if got[2].AuthorLogin != "" {
		t.Errorf("an unlinked author has no login: %+v", got[2])
	}
	limited, _ := c.FileCommits(context.Background(), "o", "n", "head2", "chat.py", 1)
	if len(limited) != 1 {
		t.Errorf("limit 1 gave %d commits", len(limited))
	}
}

func TestCommitDetailCountsLinesAndFiles(t *testing.T) {
	var calls int32
	c := historyServer(t, &calls)
	d, err := c.CommitDetail(context.Background(), "o", "n", "aaa")
	if err != nil {
		t.Fatal(err)
	}
	if d.Additions != 120 || d.Deletions != 4 || d.FilesChanged != 2 || d.Message != "Add chat" ||
		!d.CommittedAt.Equal(time.Date(2026, 3, 3, 10, 0, 0, 0, time.UTC)) {
		t.Errorf("detail = %+v", d)
	}
}

func TestPushesAreOldestFirstWithoutDeletions(t *testing.T) {
	var calls int32
	c := historyServer(t, &calls)
	p, err := c.Pushes(context.Background(), "o", "n", "main", 3)
	if err != nil {
		t.Fatal(err)
	}
	if len(p) != 2 || p[0].After != "ccc" || p[0].Before != "" || p[1].After != "aaa" || p[1].Before != "ccc" {
		t.Errorf("pushes = %+v", p)
	}
}

func TestPushTimes(t *testing.T) {
	t1 := time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC)
	t2 := t1.Add(24 * time.Hour)
	graph := map[string][]string{"d": {"c"}, "c": {"b", "x"}, "x": {"a"}, "b": {"a"}, "a": {}}
	got := PushTimes([]Push{{After: "b", At: t1}, {Before: "b", After: "d", At: t2}}, graph)
	want := map[string]time.Time{"a": t1, "b": t1, "x": t2, "c": t2, "d": t2}
	for k, v := range want {
		if !got[k].Equal(v) {
			t.Errorf("%s pushed at %v, want %v", k, got[k], v)
		}
	}

	// The records start mid-history: what was already there before the first recorded push gets no push time.
	got = PushTimes([]Push{{Before: "b", After: "d", At: t2}}, graph)
	if _, ok := got["a"]; ok {
		t.Error("a commit older than the records got a push time")
	}
	if _, ok := got["b"]; ok {
		t.Error("the first push's starting point got a push time")
	}
	if !got["x"].Equal(t2) || !got["d"].Equal(t2) {
		t.Errorf("new commits of the push: %v", got)
	}
}

func TestIsBotLogin(t *testing.T) {
	for login, want := range map[string]bool{
		"dependabot[bot]": true, "github-actions": true, "Renovate": true, "asha": false, "botanist": false,
	} {
		if IsBotLogin(login) != want {
			t.Errorf("IsBotLogin(%q) = %v", login, !want)
		}
	}
}

func TestNextPageStaysOnTheAPIHost(t *testing.T) {
	c := NewClient("https://api.github.com", "tok")
	if c.sameHost("https://evil.example/repos/x") != "" {
		t.Error("a next page on another host must not be followed")
	}
	if c.sameHost("https://api.github.com/repos/o/n/commits?page=2") == "" {
		t.Error("a next page on the API host should be followed")
	}
	if got := nextLink(`<https://api.github.com/x?page=2>; rel="next", <https://api.github.com/x?page=5>; rel="last"`); got != "https://api.github.com/x?page=2" {
		t.Errorf("nextLink = %q", got)
	}
	if c := NewClient("https://ghe.example/api/v3", ""); c.graphQLURL() != "https://ghe.example/api/graphql" {
		t.Errorf("enterprise GraphQL address = %q", c.graphQLURL())
	}
}
