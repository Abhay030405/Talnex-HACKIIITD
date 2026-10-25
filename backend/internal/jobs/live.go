package jobs

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"
)

// liveKinds are the targets the live view shows (docs/live_events.md). Other targets send nothing.
var liveKinds = map[string]bool{"project": true, "candidate_project": true, "candidate": true, "event": true}

// emitLive sends one live event about a job, the same shape the Python worker sends (ai/talnex_ai/live/events.py):
// a NOTIFY on "live" for open streams, and a saved row for replays. A failure is logged, never returned.
func (w *Worker) emitLive(ctx context.Context, job *Job, kind string, data map[string]any) {
	if w.Pool == nil || !liveKinds[job.TargetType] {
		return
	}
	ev := map[string]any{
		"v": 1, "kind": kind, "at": time.Now().UTC().Format(time.RFC3339Nano),
		"subject": map[string]string{"kind": job.TargetType, "id": job.TargetID},
		"job_id":  job.ID, "stage": job.Type, "run_number": job.RunNumber, "data": data,
	}
	if job.Pipeline != nil {
		ev["pipeline"] = *job.Pipeline
	}
	payload, err := json.Marshal(ev)
	if err != nil {
		return
	}
	if _, err := w.Pool.Exec(ctx, `SELECT pg_notify('live', $1)`, string(payload)); err != nil {
		w.Log.Warn("live event not sent", "kind", kind, "err", err)
		return
	}
	if _, err := w.Pool.Exec(ctx, `INSERT INTO live_events (subject_kind, subject_id, job_id, kind, payload)
		VALUES ($1, $2::uuid, $3::uuid, $4, $5::jsonb)`, job.TargetType, job.TargetID, job.ID, kind, payload); err != nil {
		w.Log.Warn("live event not saved", "kind", kind, "err", err)
	}
}

// summaryOf is a short line of what a stage found, from the plain values in its result (like summary_of in Python).
func summaryOf(result map[string]any) string {
	keys := make([]string, 0, len(result))
	for k := range result {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var parts []string
	for _, k := range keys {
		if k == "skipped" || k == "reason" || strings.HasSuffix(k, "_id") || strings.HasSuffix(k, "_ids") {
			continue
		}
		var v string
		switch x := result[k].(type) {
		case bool:
			v = map[bool]string{true: "yes", false: "no"}[x]
		case string:
			if len(x) > 60 {
				continue
			}
			v = x
		case int, int64, float64, float32:
			v = fmt.Sprint(x)
		default:
			continue
		}
		parts = append(parts, strings.ReplaceAll(k, "_", " ")+" "+v)
		if len(parts) == 6 {
			break
		}
	}
	return strings.Join(parts, ", ")
}
