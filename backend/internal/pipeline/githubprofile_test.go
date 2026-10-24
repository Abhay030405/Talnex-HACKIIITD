package pipeline_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
)

var profileNow = time.Date(2026, 10, 15, 12, 0, 0, 0, time.UTC)

func at(s string) time.Time {
	t, err := time.Parse("2006-01-02", s)
	if err != nil {
		panic(err)
	}
	return t
}

func commitsOn(dates ...string) []github.Commit {
	out := make([]github.Commit, len(dates))
	for i, d := range dates {
		out[i] = github.Commit{SHA: d, Date: at(d)}
	}
	return out
}

func TestSummarizeGithubProfileReadsTheShapeOfAnAccount(t *testing.T) {
	u := github.User{Login: "asha", CreatedAt: at("2024-10-15"), PublicRepos: 4, Followers: 7}
	repos := []github.Repo{
		{FullName: "asha/shop", Language: "TypeScript"},
		{FullName: "asha/notes", Language: "Go"},
		{FullName: "asha/old", Language: "Go"},
		{FullName: "asha/react", Language: "JavaScript", Fork: true},
	}
	commits := map[string][]github.Commit{
		// six commits, all on one day: the "most on one day" pattern
		"asha/shop": commitsOn("2026-09-01", "2026-09-01", "2026-09-01", "2026-09-01", "2026-09-01", "2026-09-01"),
		// three commits over two months
		"asha/notes": commitsOn("2026-01-10", "2026-01-11", "2026-03-05"),
	}
	f := pipeline.SummarizeGithubProfile(u, repos, commits, profileNow)

	if f.Account != "asha" || f.AccountAgeDays != 730 || f.Originals != 3 || f.Forks != 1 {
		t.Fatalf("account facts wrong: %+v", f)
	}
	if f.Languages["Go"] != 2 || f.Languages["TypeScript"] != 1 || f.Languages["JavaScript"] != 0 {
		t.Errorf("languages = %v (forks must not count)", f.Languages)
	}
	if f.ReposSampled != 2 || f.CommitsSampled != 9 || f.OneDayRepos != 1 {
		t.Errorf("sampled=%d commits=%d oneDay=%d", f.ReposSampled, f.CommitsSampled, f.OneDayRepos)
	}
	if len(f.Months) != 12 || f.Months[0].Month != "2025-11" || f.Months[11].Month != "2026-10" {
		t.Fatalf("months = %v", f.Months)
	}
	// Active: 2026-01, 2026-03, 2026-09. Quiet run: 2026-04 to 2026-08 is 5 months.
	if f.ActiveMonths != 3 || f.LongestQuietMonths != 5 {
		t.Errorf("active=%d quiet=%d", f.ActiveMonths, f.LongestQuietMonths)
	}
	for _, p := range f.Repos {
		switch p.Repo {
		case "asha/shop":
			if !p.MostOnOneDay || p.ActiveDays != 1 || p.BusiestDayShare != 1 {
				t.Errorf("shop = %+v", p)
			}
		case "asha/notes":
			if p.MostOnOneDay || p.ActiveDays != 3 {
				t.Errorf("notes = %+v", p)
			}
		}
	}
}

func TestAFewCommitsOnOneDayAreNotAPattern(t *testing.T) {
	f := pipeline.SummarizeGithubProfile(github.User{Login: "a"}, []github.Repo{{FullName: "a/x"}},
		map[string][]github.Commit{"a/x": commitsOn("2026-09-01", "2026-09-01")}, profileNow)
	if f.OneDayRepos != 0 {
		t.Errorf("two commits on one day must not count as a pattern: %+v", f.Repos)
	}
}

// fakeGithub answers like api.github.com for the account "asha" (found), "ghost" (unknown) and "busy" (rate limit).
func fakeGithub(t *testing.T) *github.Client {
	t.Helper()
	write := func(w http.ResponseWriter, code int, body string) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(code)
		_, _ = w.Write([]byte(body))
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/users/asha", func(w http.ResponseWriter, r *http.Request) {
		write(w, 200, `{"login":"asha","created_at":"2024-10-15T00:00:00Z","public_repos":3,"followers":2}`)
	})
	mux.HandleFunc("/users/ghost", func(w http.ResponseWriter, r *http.Request) { write(w, 404, `{"message":"Not Found"}`) })
	mux.HandleFunc("/users/busy", func(w http.ResponseWriter, r *http.Request) { write(w, 429, `{"message":"slow down"}`) })
	mux.HandleFunc("/users/asha/repos", func(w http.ResponseWriter, r *http.Request) {
		write(w, 200, `[
			{"full_name":"asha/shop","language":"TypeScript","pushed_at":"2026-09-01T00:00:00Z"},
			{"full_name":"asha/empty","pushed_at":"2026-09-01T00:00:00Z"},
			{"full_name":"asha/ancient","language":"C","pushed_at":"2020-01-01T00:00:00Z"},
			{"full_name":"asha/react","fork":true,"pushed_at":"2026-09-01T00:00:00Z"}]`)
	})
	mux.HandleFunc("/repos/asha/shop/commits", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("author") != "asha" || r.URL.Query().Get("since") == "" {
			t.Errorf("commits asked without author or since: %s", r.URL.RawQuery)
		}
		write(w, 200, `[{"sha":"a","commit":{"committer":{"date":"2026-09-01T10:00:00Z"}}},
			{"sha":"b","commit":{"committer":{"date":"2026-08-02T10:00:00Z"}}}]`)
	})
	mux.HandleFunc("/repos/asha/empty/commits", func(w http.ResponseWriter, r *http.Request) { write(w, 409, `{"message":"Git Repository is empty."}`) })
	mux.HandleFunc("/repos/", func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("unexpected call %s: forks and repos idle for a year are not read", r.URL.Path)
		write(w, 404, `{}`)
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return github.NewClient(srv.URL, "")
}

func candidateWithRepos(t *testing.T, repos ...string) string {
	t.Helper()
	cand := candidateWithHandles(t, `{}`)
	for _, r := range repos {
		if _, err := dbtest.Pool(t).Exec(context.Background(),
			`INSERT INTO candidate_projects (candidate_id, name, repo_url) VALUES ($1::uuid, 'p', NULLIF($2, ''))`, cand, r); err != nil {
			t.Fatal(err)
		}
	}
	return cand
}

func runGithubProfile(t *testing.T, cand string) (map[string]any, error) {
	t.Helper()
	h := pipeline.GithubProfile(dbtest.Pool(t), fakeGithub(t), func() time.Time { return profileNow })
	return h(context.Background(), &jobs.Job{TargetType: "candidate", TargetID: cand})
}

func TestGithubProfileReadsTheAccountThatOwnsMostResumeRepos(t *testing.T) {
	// "asha" and "Asha" are one account (GitHub names ignore case), so asha owns two of the three repos.
	cand := candidateWithRepos(t, "https://github.com/bob/one", "github.com/asha/notes", "https://github.com/Asha/shop", "")
	for i := 0; i < 2; i++ { // safe to run twice
		out, err := runGithubProfile(t, cand)
		if err != nil {
			t.Fatal(err)
		}
		if out["found"] != true || out["account"] != "asha" || out["originals"] != 3 || out["forks"] != 1 || out["repos_sampled"] != 1 {
			t.Fatalf("summary wrong: %v", out)
		}
	}
	var n int
	var weight, active string
	err := dbtest.Pool(t).QueryRow(context.Background(),
		`SELECT count(*) OVER (), weight, evidence->>'active_months' FROM coding_signals WHERE candidate_id = $1::uuid AND site = 'github'`, cand).
		Scan(&n, &weight, &active)
	if err != nil {
		t.Fatal(err)
	}
	if n != 1 || weight != "not_suspicious" || active != "2" {
		t.Errorf("rows=%d weight=%s active_months=%s", n, weight, active)
	}
}

func TestGithubProfileWithNoRepoOnTheResumeIsSkipped(t *testing.T) {
	out, err := runGithubProfile(t, candidateWithRepos(t, "", "https://gitlab.com/asha/x"))
	if err != nil || out["skipped"] != true {
		t.Errorf("got %v, %v", out, err)
	}
}

func TestGithubProfileUnknownAccountIsNotAnError(t *testing.T) {
	cand := candidateWithRepos(t, "https://github.com/ghost/x")
	out, err := runGithubProfile(t, cand)
	if err != nil || out["found"] != false {
		t.Fatalf("got %v, %v", out, err)
	}
	var n int
	_ = dbtest.Pool(t).QueryRow(context.Background(), `SELECT count(*) FROM coding_signals WHERE candidate_id = $1::uuid`, cand).Scan(&n)
	if n != 0 {
		t.Errorf("saved %d rows for an unknown account", n)
	}
}

func TestGithubProfileRateLimitIsRetried(t *testing.T) {
	if _, err := runGithubProfile(t, candidateWithRepos(t, "https://github.com/busy/x")); !errors.Is(err, github.ErrRateLimited) {
		t.Errorf("err = %v, want a rate limit error so the queue retries", err)
	}
}
