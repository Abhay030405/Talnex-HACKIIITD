// Package pipeline holds the names of pipelines and stages, and the Go stage handlers.
// The stage order itself is data in the pipeline_stages table (migration 000007), so the queue
// can add the next stage in the same database step for both Go and Python jobs.
package pipeline

import (
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/codeforces"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/github"
	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
)

// Pipeline names, as stored in pipeline_stages.pipeline.
const (
	Hackathon = "hackathon"
	Recruiter = "recruiter"
	// RecruiterCandidate reads a resume and starts the Recruiter pipeline for each project on it.
	RecruiterCandidate = "recruiter_candidate"
	// RecruiterCoding reads a candidate's coding profiles (Codeforces first). Data only, not yet chained.
	RecruiterCoding = "recruiter_coding"
	SelfTest        = "selftest"
)

// Go stage names. Python stages are named in ai/talnex_ai/worker.
const (
	StageSelfTestB   = "selftest_b"
	StageGithubCheck = "github_check"
	StageCodeforces  = "codeforces"
)

// GoHandlers returns the stage handlers that run in the Go workers.
// Later phases add their handlers here (GitHub data, Codeforces, cleanup).
func GoHandlers(pool *pgxpool.Pool, gh *github.Client, cf *codeforces.Client, files PrefixDeleter, history HistoryLimits) map[string]jobs.Handler {
	return map[string]jobs.Handler{
		StageSelfTestB:     selfTestB,
		StageGithubCheck:   GithubCheck(pool, gh),
		StageCodeforces:    Codeforces(pool, cf),
		StageEventDates:    EventDates(pool, gh),
		StageSponsorFiles:  SponsorFiles(pool, gh),
		StageResumeCleanup: ResumeCleanup(pool, files),
		StageGithubHistory: GithubHistory(pool, gh, history),
	}
}
