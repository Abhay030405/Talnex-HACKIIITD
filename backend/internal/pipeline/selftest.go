package pipeline

import (
	"context"

	"github.com/Abhay030405/Talnex-HACKIIITD/backend/internal/jobs"
)

// selfTestB is the Go step in the selftest pipeline (python -> go -> python).
// It proves a job can hop from a Python worker to a Go worker and back.
func selfTestB(_ context.Context, job *jobs.Job) (map[string]any, error) {
	return map[string]any{"stage": StageSelfTestB, "runner": jobs.RunnerGo, "target": job.TargetID}, nil
}
