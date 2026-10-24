package pipeline_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/codeforces"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/db/dbtest"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/pipeline"
)

// fakeCodeforces answers like codeforces.com/api for the handles "asha" (found), "ghost" (unknown) and "busy" (rate limit).
func fakeCodeforces(t *testing.T) *codeforces.Client {
	t.Helper()
	write := func(w http.ResponseWriter, code int, body string) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(code)
		_, _ = w.Write([]byte(body))
	}
	handle := func(r *http.Request) string {
		if h := r.URL.Query().Get("handle"); h != "" {
			return h
		}
		return r.URL.Query().Get("handles")
	}
	guard := func(w http.ResponseWriter, r *http.Request) bool {
		switch handle(r) {
		case "ghost":
			write(w, 400, `{"status":"FAILED","comment":"handles: User with handle ghost not found"}`)
		case "busy":
			write(w, 429, `Too many requests`)
		default:
			return true
		}
		return false
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/user.info", func(w http.ResponseWriter, r *http.Request) {
		if guard(w, r) {
			write(w, 200, `{"status":"OK","result":[{"handle":"asha","rating":1523,"maxRating":1610,"rank":"specialist","maxRank":"expert"}]}`)
		}
	})
	mux.HandleFunc("/user.rating", func(w http.ResponseWriter, r *http.Request) {
		if guard(w, r) {
			write(w, 200, `{"status":"OK","result":[{"contestId":1,"oldRating":0,"newRating":900},{"contestId":2,"oldRating":900,"newRating":1100}]}`)
		}
	})
	mux.HandleFunc("/user.status", func(w http.ResponseWriter, r *http.Request) {
		if guard(w, r) {
			// Problem 1A is accepted twice and counts once; 1B failed; 2A accepted.
			write(w, 200, `{"status":"OK","result":[
				{"creationTimeSeconds":1760000000,"verdict":"OK","problem":{"contestId":2,"index":"A","name":"Two"}},
				{"creationTimeSeconds":1750000000,"verdict":"WRONG_ANSWER","problem":{"contestId":1,"index":"B","name":"B"}},
				{"creationTimeSeconds":1740000000,"verdict":"OK","problem":{"contestId":1,"index":"A","name":"A"}},
				{"creationTimeSeconds":1730000000,"verdict":"OK","problem":{"contestId":1,"index":"A","name":"A"}}]}`)
		}
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return codeforces.NewClient(srv.URL)
}

func candidateWithHandles(t *testing.T, handles string) string {
	t.Helper()
	pool := dbtest.Pool(t)
	ctx := context.Background()
	var owner, cand string
	if err := pool.QueryRow(ctx, `INSERT INTO users (email) VALUES ($1) RETURNING id::text`, uuid.NewString()+"@example.com").Scan(&owner); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `INSERT INTO candidates (owner_id, label, coding_handles) VALUES ($1::uuid, 'c', $2::jsonb) RETURNING id::text`,
		owner, handles).Scan(&cand); err != nil {
		t.Fatal(err)
	}
	return cand
}

func runCodeforces(t *testing.T, cand string) (map[string]any, error) {
	t.Helper()
	return pipeline.Codeforces(dbtest.Pool(t), fakeCodeforces(t))(context.Background(), &jobs.Job{TargetType: "candidate", TargetID: cand})
}

func TestCodeforcesSavesTheProfileOnce(t *testing.T) {
	cand := candidateWithHandles(t, `{"codeforces":"asha"}`)
	for i := 0; i < 2; i++ { // safe to run twice
		out, err := runCodeforces(t, cand)
		if err != nil {
			t.Fatal(err)
		}
		if out["found"] != true || out["rating"] != 1523 || out["max_rating"] != 1610 || out["rank"] != "specialist" ||
			out["contests"] != 2 || out["solved_problems"] != 2 || out["recent_activity"] != "2025-10-09" {
			t.Fatalf("summary wrong: %v", out)
		}
	}
	var n int
	var weight, solved string
	err := dbtest.Pool(t).QueryRow(context.Background(),
		`SELECT count(*) OVER (), weight, evidence->>'solved_problems' FROM coding_signals WHERE candidate_id = $1::uuid AND site = 'codeforces'`, cand).
		Scan(&n, &weight, &solved)
	if err != nil {
		t.Fatal(err)
	}
	if n != 1 || weight != "not_suspicious" || solved != "2" {
		t.Errorf("rows=%d weight=%s solved=%s", n, weight, solved)
	}
}

func TestCodeforcesUnknownHandleIsNotAnError(t *testing.T) {
	cand := candidateWithHandles(t, `{"codeforces":"ghost"}`)
	out, err := runCodeforces(t, cand)
	if err != nil {
		t.Fatal(err)
	}
	if out["found"] != false || out["handle"] != "ghost" {
		t.Errorf("got %v", out)
	}
	var n int
	_ = dbtest.Pool(t).QueryRow(context.Background(), `SELECT count(*) FROM coding_signals WHERE candidate_id = $1::uuid`, cand).Scan(&n)
	if n != 0 {
		t.Errorf("saved %d rows for an unknown handle", n)
	}
}

func TestCodeforcesRateLimitIsRetried(t *testing.T) {
	cand := candidateWithHandles(t, `{"codeforces":"busy"}`)
	if _, err := runCodeforces(t, cand); !errors.Is(err, codeforces.ErrRateLimited) {
		t.Errorf("err = %v, want a rate limit error so the queue retries", err)
	}
}

func TestCodeforcesNoHandleIsSkipped(t *testing.T) {
	for _, handles := range []string{`{}`, `{"leetcode":"x"}`, `{"codeforces":"  "}`} {
		out, err := runCodeforces(t, candidateWithHandles(t, handles))
		if err != nil {
			t.Fatal(err)
		}
		if out["skipped"] != true || out["reason"] != "no Codeforces handle given" {
			t.Errorf("%s: got %v", handles, out)
		}
	}
}

func TestCodeforcesNeedsACandidate(t *testing.T) {
	if _, err := pipeline.Codeforces(dbtest.Pool(t), fakeCodeforces(t))(context.Background(), &jobs.Job{TargetType: "project", TargetID: uuid.NewString()}); err == nil {
		t.Error("expected an error for a project")
	}
}
