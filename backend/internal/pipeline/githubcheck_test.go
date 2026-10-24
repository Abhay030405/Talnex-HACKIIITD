package pipeline_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
)

// fakeGitHub answers like api.github.com for a few repositories.
func fakeGitHub(t *testing.T) *github.Client {
	t.Helper()
	mux := http.NewServeMux()
	write := func(w http.ResponseWriter, body string) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}
	mux.HandleFunc("/repos/asha/tinytools", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-token" {
			http.Error(w, "no token", http.StatusUnauthorized)
			return
		}
		write(w, `{"full_name":"asha/tinytools","private":false,"fork":true,"parent":{"full_name":"someone/starter"},
			"created_at":"2026-03-01T10:00:00Z","pushed_at":"2026-09-01T10:00:00Z","default_branch":"main","stargazers_count":3,"size":120}`)
	})
	mux.HandleFunc("/repos/asha/tinytools/languages", func(w http.ResponseWriter, _ *http.Request) {
		write(w, `{"JavaScript":9000,"HTML":1500}`)
	})
	mux.HandleFunc("/repos/asha/tinytools/git/trees/main", func(w http.ResponseWriter, _ *http.Request) {
		write(w, `{"truncated":false,"tree":[
			{"path":"README.md","type":"blob"},{"path":"package.json","type":"blob"},{"path":"api","type":"tree"},
			{"path":"api/convert.js","type":"blob"},{"path":"Dockerfile","type":"blob"},{"path":"web/package.json","type":"blob"}]}`)
	})
	mux.HandleFunc("/repos/asha/empty", func(w http.ResponseWriter, _ *http.Request) {
		write(w, `{"full_name":"asha/empty","default_branch":"main","created_at":"2026-03-01T10:00:00Z","pushed_at":"2026-03-01T10:00:00Z"}`)
	})
	mux.HandleFunc("/repos/asha/empty/languages", func(w http.ResponseWriter, _ *http.Request) { write(w, `{}`) })
	mux.HandleFunc("/repos/asha/empty/git/trees/main", func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, `{"message":"Git Repository is empty."}`, http.StatusConflict)
	})
	mux.HandleFunc("/repos/asha/busy", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("X-RateLimit-Remaining", "0")
		http.Error(w, `{"message":"rate limit"}`, http.StatusForbidden)
	})
	srv := httptest.NewServer(mux) // anything else: 404
	t.Cleanup(srv.Close)
	return github.NewClient(srv.URL, "test-token")
}

func subjectWithRepo(t *testing.T, kind, repo string) string {
	t.Helper()
	pool := dbtest.Pool(t)
	ctx := context.Background()
	var owner string
	if err := pool.QueryRow(ctx, `INSERT INTO users (email) VALUES ($1) RETURNING id::text`, uuid.NewString()+"@example.com").Scan(&owner); err != nil {
		t.Fatal(err)
	}
	var id string
	if kind == "project" {
		var ev string
		if err := pool.QueryRow(ctx, `INSERT INTO events (owner_id, name, mode, starts_at, ends_at)
			VALUES ($1::uuid, 'E', 'open_theme', now(), now() + interval '1 day') RETURNING id::text`, owner).Scan(&ev); err != nil {
			t.Fatal(err)
		}
		if err := pool.QueryRow(ctx, `INSERT INTO projects (event_id, team_name, repo_url) VALUES ($1::uuid, 'T', NULLIF($2, '')) RETURNING id::text`,
			ev, repo).Scan(&id); err != nil {
			t.Fatal(err)
		}
		return id
	}
	var cand string
	if err := pool.QueryRow(ctx, `INSERT INTO candidates (owner_id, label) VALUES ($1::uuid, 'c') RETURNING id::text`, owner).Scan(&cand); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `INSERT INTO candidate_projects (candidate_id, name, repo_url) VALUES ($1::uuid, 'P', NULLIF($2, '')) RETURNING id::text`,
		cand, repo).Scan(&id); err != nil {
		t.Fatal(err)
	}
	return id
}

func run(t *testing.T, kind, repo string) (map[string]any, error) {
	t.Helper()
	handler := pipeline.GithubCheck(dbtest.Pool(t), fakeGitHub(t))
	return handler(context.Background(), &jobs.Job{TargetType: kind, TargetID: subjectWithRepo(t, kind, repo)})
}

func TestRepoFactsForBothKindsOfSubject(t *testing.T) {
	for _, kind := range []string{"project", "candidate_project"} {
		t.Run(kind, func(t *testing.T) {
			out, err := run(t, kind, "https://github.com/asha/tinytools")
			if err != nil {
				t.Fatal(err)
			}
			if out["found"] != true || out["repo"] != "asha/tinytools" || out["fork"] != true || out["forked_from"] != "someone/starter" {
				t.Errorf("repo facts wrong: %v", out)
			}
			if out["has_readme"] != true || out["file_count"] != 5 {
				t.Errorf("files wrong: readme=%v count=%v", out["has_readme"], out["file_count"])
			}
			deps := out["dependency_files"].([]string)
			if len(deps) != 2 || deps[0] != "package.json" {
				t.Errorf("dependency files = %v", deps)
			}
			if runs := out["run_files"].([]string); len(runs) != 1 || runs[0] != "Dockerfile" {
				t.Errorf("run files = %v", runs)
			}
			if langs := out["languages"].(map[string]int); langs["JavaScript"] != 9000 {
				t.Errorf("languages = %v", langs)
			}
		})
	}
}

func TestMissingRepositoriesAreNotErrors(t *testing.T) {
	cases := map[string]string{
		"":                                       "no repository link",
		"https://gitlab.com/asha/tinytools":      "not a GitHub repository",
		"https://github.com/asha/does-not-exist": "does not exist or is private",
		"https://github.com/asha":                "not a GitHub repository",
	}
	for link, want := range cases {
		out, err := run(t, "candidate_project", link)
		if err != nil {
			t.Fatalf("%q: %v", link, err)
		}
		if out["found"] != false || !strings.Contains(out["reason"].(string), want) {
			t.Errorf("%q: %v, want a reason containing %q", link, out, want)
		}
	}
}

func TestEmptyRepositoryHasNoFiles(t *testing.T) {
	out, err := run(t, "project", "https://github.com/asha/empty.git")
	if err != nil || out["found"] != true || out["empty"] != true || out["file_count"] != 0 {
		t.Errorf("empty repo: %v %v", out, err)
	}
}

func TestRateLimitFailsSoTheQueueTriesAgain(t *testing.T) {
	_, err := run(t, "project", "https://github.com/asha/busy")
	if !errors.Is(err, github.ErrRateLimited) {
		t.Errorf("err = %v, want a rate limit error", err)
	}
}

func TestAfterTheLastTryGitHubTroubleEndsAsCouldNotCheck(t *testing.T) {
	handler := pipeline.GithubCheck(dbtest.Pool(t), fakeGitHub(t))
	id := subjectWithRepo(t, "project", "https://github.com/asha/busy")
	early, err := handler(context.Background(), &jobs.Job{TargetType: "project", TargetID: id, Tries: 1, MaxTries: 3})
	if err == nil {
		t.Fatalf("an early try must fail so it is tried again, got %v", early)
	}
	last, err := handler(context.Background(), &jobs.Job{TargetType: "project", TargetID: id, Tries: 3, MaxTries: 3})
	if err != nil || last["found"] != false || !strings.Contains(last["reason"].(string), "could not be reached") {
		t.Errorf("last try: %v %v", last, err)
	}
}

func TestWrongKindOfTargetIsRefused(t *testing.T) {
	handler := pipeline.GithubCheck(dbtest.Pool(t), fakeGitHub(t))
	if _, err := handler(context.Background(), &jobs.Job{TargetType: "candidate", TargetID: uuid.NewString()}); err == nil {
		t.Error("a candidate is not a project; want an error")
	}
}

func TestParseRepoURL(t *testing.T) {
	good := map[string][2]string{
		"https://github.com/a/b":           {"a", "b"},
		"github.com/a/b":                   {"a", "b"},
		"https://www.github.com/a/b.git":   {"a", "b"},
		"https://github.com/a/b/tree/main": {"a", "b"},
	}
	for in, want := range good {
		if o, n, ok := github.ParseRepoURL(in); !ok || o != want[0] || n != want[1] {
			t.Errorf("%q -> %q %q %v", in, o, n, ok)
		}
	}
	for _, in := range []string{"", "https://github.com", "https://github.com/a", "https://gitlab.com/a/b", "not a url"} {
		if _, _, ok := github.ParseRepoURL(in); ok {
			t.Errorf("%q should not parse", in)
		}
	}
}
