package pipeline_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
)

// historyGitHub answers like api.github.com for asha/chatapp: two commits, blame of two files, push records.
func historyGitHub(t *testing.T, withPushes bool) *github.Client {
	t.Helper()
	mux := http.NewServeMux()
	write := func(w http.ResponseWriter, body string) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}
	mux.HandleFunc("GET /repos/asha/chatapp", func(w http.ResponseWriter, _ *http.Request) {
		write(w, `{"full_name":"asha/chatapp","fork":true,"parent":{"full_name":"someone/starter"},"default_branch":"main",
			"created_at":"2026-03-01T10:00:00Z","pushed_at":"2026-03-04T10:00:00Z"}`)
	})
	mux.HandleFunc("GET /repos/asha/chatapp/commits", func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Query().Get("path") {
		case "":
			write(w, `[{"sha":"c2","commit":{"message":"Add memory","committer":{"date":"2026-03-03T10:00:00Z"}},"parents":[{"sha":"c1"}]},
			           {"sha":"c1","commit":{"message":"Start","committer":{"date":"2026-03-01T10:00:00Z"}},"parents":[]}]`)
		case "chat/service.py":
			write(w, `[{"sha":"c2"},{"sha":"c1"}]`)
		default:
			write(w, `[{"sha":"c1"}]`)
		}
	})
	detail := map[string]string{
		"c1": `{"sha":"c1","commit":{"message":"Start\n\nbody","committer":{"date":"2026-03-01T10:00:00Z"}},
		        "author":{"login":"asha","type":"User"},"parents":[],"stats":{"additions":300,"deletions":0},"files":[{"filename":"a"},{"filename":"b"}]}`,
		"c2": `{"sha":"c2","commit":{"message":"Add memory","committer":{"date":"2026-03-03T10:00:00Z"}},
		        "author":null,"parents":[{"sha":"c1"}],"stats":{"additions":20,"deletions":5},"files":[{"filename":"chat/service.py"}]}`,
	}
	mux.HandleFunc("GET /repos/asha/chatapp/commits/{sha}", func(w http.ResponseWriter, r *http.Request) {
		body, ok := detail[r.PathValue("sha")]
		if !ok {
			http.NotFound(w, r)
			return
		}
		write(w, body)
	})
	mux.HandleFunc("GET /repos/asha/chatapp/activity", func(w http.ResponseWriter, _ *http.Request) {
		if !withPushes {
			write(w, `[]`)
			return
		}
		write(w, `[{"before":"0000000000000000000000000000000000000000","after":"c1","timestamp":"2026-03-01T11:00:00Z","activity_type":"branch_creation"},
		           {"before":"c1","after":"c2","timestamp":"2026-03-04T09:00:00Z","activity_type":"push"}]`)
	})
	mux.HandleFunc("POST /graphql", func(w http.ResponseWriter, r *http.Request) {
		var q struct {
			Query     string         `json:"query"`
			Variables map[string]any `json:"variables"`
		}
		_ = json.NewDecoder(r.Body).Decode(&q)
		switch {
		case strings.Contains(q.Query, "totalCount"):
			write(w, `{"data":{"repository":{"object":{"history":{"totalCount":2}}}}}`)
		case q.Variables["path"] == "chat/service.py":
			write(w, `{"data":{"repository":{"object":{"blame":{"ranges":[
				{"startingLine":1,"endingLine":39,"commit":{"oid":"c1"}},
				{"startingLine":40,"endingLine":60,"commit":{"oid":"c2"}},
				{"startingLine":61,"endingLine":200,"commit":{"oid":"c1"}}]}}}}}`)
		case q.Variables["path"] == "routes/chat.py":
			write(w, `{"data":{"repository":{"object":{"blame":{"ranges":[{"startingLine":1,"endingLine":50,"commit":{"oid":"c1"}}]}}}}}`)
		default:
			write(w, `{"data":{"repository":{"object":{"blame":null}}},"errors":[{"message":"Could not resolve file for path"}]}`)
		}
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return github.NewClient(srv.URL, "test-token")
}

func addClaimMap(t *testing.T, kind, subject, files, sha string) string {
	t.Helper()
	pool := dbtest.Pool(t)
	ctx := context.Background()
	column := "project_id"
	if kind == "candidate_project" {
		column = "candidate_project_id"
	}
	var claim string
	if err := pool.QueryRow(ctx, `INSERT INTO claims (`+column+`, text, claim_group, importance, source)
		VALUES ($1::uuid, 'chat remembers', 'Core', 3, 'readme') RETURNING id::text`, subject).Scan(&claim); err != nil {
		t.Fatal(err)
	}
	if _, err := pool.Exec(ctx, `INSERT INTO claim_code_maps (claim_id, files, found_by, confidence, commit_sha)
		VALUES ($1::uuid, $2::jsonb, 'model', 0.9, NULLIF($3, ''))`, claim, files, sha); err != nil {
		t.Fatal(err)
	}
	return claim
}

var bigLimits = pipeline.HistoryLimits{FilesPerClaim: 5, ClaimsPerProject: 5, CommitsPerFile: 50, BranchCommits: 100}

func TestHistoryBlamesOnlyTheMappedLinesAndUsesPushTimes(t *testing.T) {
	for _, kind := range []string{"project", "candidate_project"} {
		t.Run(kind, func(t *testing.T) {
			subject := subjectWithRepo(t, kind, "https://github.com/asha/chatapp")
			claim := addClaimMap(t, kind, subject, `[{"path":"chat/service.py","start":35,"end":45,"why":"memory"},
				{"path":"./chat/service.py","start":44,"end":50},{"path":"routes/chat.py","start":12,"end":20},
				{"path":"gone.py","start":1,"end":3}]`, "")
			out, err := pipeline.GithubHistory(dbtest.Pool(t), historyGitHub(t, true), bigLimits)(context.Background(),
				&jobs.Job{TargetType: kind, TargetID: subject})
			if err != nil {
				t.Fatal(err)
			}
			if out["found"] != true || out["repo"] != "asha/chatapp" || out["commit_sha"] != "c2" || out["date_source"] != "push" ||
				out["is_fork"] != true || out["parent_repo"] != "someone/starter" || out["repo_commit_count"] != 2 {
				t.Fatalf("result = %v", out)
			}
			raw, _ := json.Marshal(out["files"])
			want := `[{"blame":[],"missing":true,"path":"gone.py"},` +
				`{"blame":[{"start":12,"end":20,"sha":"c1"}],"path":"routes/chat.py"},` +
				`{"blame":[{"start":35,"end":39,"sha":"c1"},{"start":40,"end":50,"sha":"c2"}],"path":"chat/service.py"}]`
			var gotFiles, wantFiles []map[string]any
			_ = json.Unmarshal(raw, &gotFiles)
			_ = json.Unmarshal([]byte(want), &wantFiles)
			if len(gotFiles) != 3 {
				t.Fatalf("files = %s", raw)
			}
			byPath := map[string]string{}
			for _, f := range gotFiles {
				b, _ := json.Marshal(f)
				byPath[f["path"].(string)] = string(b)
			}
			for _, f := range wantFiles {
				b, _ := json.Marshal(f)
				if byPath[f["path"].(string)] != string(b) {
					t.Errorf("%s: got %s, want %s", f["path"], byPath[f["path"].(string)], b)
				}
			}

			commits := out["commits"].(map[string]any)
			c1, c2 := commits["c1"].(map[string]any), commits["c2"].(map[string]any)
			if c1["author_login"] != "asha" || c1["message"] != "Start" || c1["additions"] != 300 || c1["files_changed"] != 2 ||
				c1["parents"] != 0 || c1["is_bot"] != false || c1["pushed_at"] != "2026-03-01T11:00:00Z" {
				t.Errorf("c1 = %v", c1)
			}
			if c2["author_login"] != nil || c2["pushed_at"] != "2026-03-04T09:00:00Z" || c2["committed_at"] != "2026-03-03T10:00:00Z" {
				t.Errorf("c2 (unlinked author) = %v", c2)
			}
			if _, leaked := out["traced_claims"]; leaked {
				t.Error("the internal list of traced claims leaked into the result")
			}
			var saved string
			if err := dbtest.Pool(t).QueryRow(context.Background(), `SELECT commit_sha FROM claim_code_maps WHERE claim_id = $1::uuid`,
				claim).Scan(&saved); err != nil || saved != "c2" {
				t.Errorf("commit_sha saved = %q, %v", saved, err)
			}
		})
	}
}

func TestHistoryWithoutPushRecordsUsesCommitDates(t *testing.T) {
	subject := subjectWithRepo(t, "project", "https://github.com/asha/chatapp")
	addClaimMap(t, "project", subject, `[{"path":"routes/chat.py","start":1,"end":5}]`, "")
	out, err := pipeline.GithubHistory(dbtest.Pool(t), historyGitHub(t, false), bigLimits)(context.Background(),
		&jobs.Job{TargetType: "project", TargetID: subject})
	if err != nil {
		t.Fatal(err)
	}
	if out["date_source"] != "commit" {
		t.Errorf("date_source = %v, want commit", out["date_source"])
	}
	if c1 := out["commits"].(map[string]any)["c1"].(map[string]any); c1["pushed_at"] != nil {
		t.Errorf("pushed_at without records = %v", c1["pushed_at"])
	}
}

func TestHistoryLimitsSkipClaimsWithTheLimitNamed(t *testing.T) {
	subject := subjectWithRepo(t, "project", "https://github.com/asha/chatapp")
	first := addClaimMap(t, "project", subject, `[{"path":"routes/chat.py","start":1,"end":5}]`, "c1")
	wide := addClaimMap(t, "project", subject, `[{"path":"a.py","start":1,"end":5},{"path":"b.py","start":1,"end":5}]`, "")
	extra := addClaimMap(t, "project", subject, `[{"path":"chat/service.py","start":1,"end":5}]`, "")
	limits := pipeline.HistoryLimits{FilesPerClaim: 1, ClaimsPerProject: 1, CommitsPerFile: 10, BranchCommits: 10}
	out, err := pipeline.GithubHistory(dbtest.Pool(t), historyGitHub(t, true), limits)(context.Background(),
		&jobs.Job{TargetType: "project", TargetID: subject})
	if err != nil {
		t.Fatal(err)
	}
	// A1 read the code at c1, so the lines are blamed at c1, not at the newest commit.
	if out["commit_sha"] != "c1" {
		t.Errorf("commit_sha = %v, want the one code locate used", out["commit_sha"])
	}
	skipped := out["skipped_claims"].([]map[string]any)
	reasons := map[string]string{}
	for _, s := range skipped {
		reasons[s["claim_id"].(string)] = s["reason"].(string)
	}
	if _, ok := reasons[first]; ok || len(skipped) != 2 {
		t.Fatalf("skipped = %v", skipped)
	}
	if !strings.Contains(reasons[wide], "more than 1 files") || !strings.Contains(reasons[extra], "more than 1 features") {
		t.Errorf("reasons = %v", reasons)
	}
}

func TestHistoryWithoutARepositoryIsNotAnError(t *testing.T) {
	for link, want := range map[string]string{
		"":                                  "no repository link",
		"https://gitlab.com/asha/chatapp":   "not a GitHub repository",
		"https://github.com/asha/not-there": "does not exist or is private",
	} {
		subject := subjectWithRepo(t, "candidate_project", link)
		out, err := pipeline.GithubHistory(dbtest.Pool(t), historyGitHub(t, true), bigLimits)(context.Background(),
			&jobs.Job{TargetType: "candidate_project", TargetID: subject})
		if err != nil {
			t.Fatalf("%q: %v", link, err)
		}
		if out["found"] != false || !strings.Contains(out["reason"].(string), want) {
			t.Errorf("%q: %v, want a reason containing %q", link, out, want)
		}
	}
}

func TestHistoryEndsAsCouldNotTraceOnTheLastTry(t *testing.T) {
	busy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("X-RateLimit-Remaining", "0")
		http.Error(w, `{"message":"rate limit"}`, http.StatusForbidden)
	}))
	defer busy.Close()
	gh := github.NewClient(busy.URL, "t")
	subject := subjectWithRepo(t, "project", "https://github.com/asha/chatapp")
	handler := pipeline.GithubHistory(dbtest.Pool(t), gh, bigLimits)
	if _, err := handler(context.Background(), &jobs.Job{TargetType: "project", TargetID: subject, Tries: 1, MaxTries: 3}); err == nil {
		t.Error("a rate limit before the last try should be retried")
	}
	out, err := handler(context.Background(), &jobs.Job{TargetType: "project", TargetID: subject, Tries: 3, MaxTries: 3})
	if err != nil || out["found"] != false {
		t.Errorf("last try: %v, %v", out, err)
	}
}
