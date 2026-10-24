# Live events: streaming what TalNex is doing

So a judge or recruiter can watch a check as it happens (the pipeline lighting up, the agent's reason for each click, each screenshot as it's taken, every verdict as it lands) instead of waiting 10–15 minutes at a spinner. The same stream is our debugging trace.

## How it fits the architecture

```
Python worker --pg_notify('live', json)--> Postgres --LISTEN live--> Go API --Server-Sent Events--> website
      |                                       ^
      +-- (optional) INSERT INTO live_events --+   for replay, once the table exists
```

- Go and Python still never call each other: the events travel on Postgres's built-in message channel.
- Sending an event never fails or slows a check. If nobody is listening, events are simply dropped.
- No schema change is needed for the live part. Replay needs one table (proposed below).

| Part | Who | Status |
|---|---|---|
| Event sender in the Python worker, hooks in the worker loop, test loop, runner, ladder and live_test stage | Arnav | built (`ai/talnex_ai/live/`) |
| Terminal viewer for debugging: `python -m talnex_ai.live.watch [--subject <id>]` | Arnav | built |
| `live_events` table (migration 26) + 7-day cleanup, and the streaming endpoint `GET /v1/live/{kind}/{id}` | Arnav | built (`backend/internal/live/`, `backend/internal/http/live.go`) |
| Local demo: mission control at `GET /v1/dev/live/view`, fed by `GET /v1/dev/live` (only with `ENABLE_DEV_ENDPOINTS=true`) | Arnav | built |
| Mission control page | Devesh | to do |

## The event

Channel: `live`. Each message is one JSON object, at most 7,500 bytes (long text is clipped; if still too big, the largest fields are dropped and named in `data.cut`).

```json
{
  "v": 1,
  "kind": "step.record",
  "at": "2026-10-24T14:02:14.123Z",
  "subject": {"kind": "project", "id": "4f6c…"},
  "job_id": "9a1e…",
  "stage": "live_test",
  "pipeline": "hackathon",
  "run_number": 1,
  "claim_id": "c71b…",
  "run_id": "e02d…",
  "data": {"number": 2, "label": "Type \"TalNex test buy milk\" into the placeholder \"What needs to be done?\"",
           "proof_key": "screens/4f6c…/e02d…/2", "box": {"x": 482, "y": 188, "w": 550, "h": 64},
           "url": "https://demo.example.com/", "expected": "…", "observed": null}
}
```

`subject.kind` is `project`, `candidate_project`, `candidate` or `event`. `job_id`, `stage`, `claim_id` and `run_id` are present when they apply.

### Kinds

| kind | when | data |
|---|---|---|
| `stage.started` | a pipeline stage starts | `try_number` |
| `stage.finished` | a stage ends | `seconds`, `skipped`, `reason` |
| `stage.failed` | a stage hit an error | `status` (`retrying` or `failed`), `error` |
| `claims.queued` | live testing starts for a subject | `total`, `todo`, `claims` [{id, text}] |
| `claim.started` | one claim starts | `text`, `group`, `importance`, `test_type`, `steps` |
| `ladder` | each rung of the never-blame ladder | `line` |
| `run.started` | a browser run starts | `try_number`, `test_type`, `steps`, `expected_result` |
| `reason` | the agent's stated reason for its next move | `step`, `text`, `looked_at_picture` |
| `step.record` | an action was done (screenshot taken) | `number`, `label`, `expected`, `observed`, `proof_key`, `box`, `url` |
| `step.result` | a plan step ended | `step`, `steps`, `result` (done/failed/blocked), `observed` |
| `run.outcome` | the run's own conclusion | `outcome`, `observed`, `stop_reason`, `actions` |
| `run.finished` | the browser closed | `outcome`, `reason`, `actions`, `cost_usd` |
| `check.started` | the blind proof check starts | `images` |
| `check` | the blind proof check answered | `outcome`, `seen`, `images` |
| `verdict` | a claim's final result was saved | `verdict`, `confidence`, `reason`, `proof_keys`, `second_check_agreed` |

`reason` is the short reason the agent states for each move (part of its answer), not hidden model reasoning.

## The streaming endpoint and the table (built)

**Endpoint:** `GET /v1/live/{subject_kind}/{subject_id}` (`project`, `candidate_project`, `candidate` or `event`), `Content-Type: text/event-stream`.
- Check the owner, like every other endpoint.
- One dedicated connection per API process runs `LISTEN live` and fans events out to the open streams for their `subject.id` (don't open a Postgres connection per viewer).
- Send each event as `event: <kind>` + `data: <json>`; a comment line (`: ping`) every 15 s keeps proxies from closing the stream.
- Turn every `proof_key` (in `step.record` and `verdict`) into a short-lived view link before sending, the same way proof screenshots are shared today, so the browser never sees storage keys or keys of any kind.
- On connect, first send the recent events from `live_events` (replay), then switch to live.
- For a whole event (mission control), stream every subject whose project belongs to that event.

**Migration** (`000026_live_events`; Python starts saving into it automatically within a minute of it existing, no restart needed):

```sql
CREATE TABLE live_events (
    id            bigserial PRIMARY KEY,
    subject_kind  text NOT NULL,
    subject_id    uuid NOT NULL,
    job_id        uuid,
    kind          text NOT NULL,
    payload       jsonb NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX live_events_subject_idx ON live_events (subject_id, id);
```
Cleanup: delete rows older than 7 days (they're a viewing aid; the real results live in `results`, `steps` and `scores`).

## For Devesh: the mission control page

Connect with `new EventSource('/api/live/…')` (through the website's own server route, so no key reaches the browser).

- **Pipeline graph:** nodes from the pipeline's stages; a node is *running* after `stage.started`, *done* after `stage.finished` (grey if `skipped`), *red* after `stage.failed` with `status: failed`.
- **Live browser:** show the screenshot from each `step.record` as it arrives. `box` is in full-page screenshot pixels: draw a ring at its centre to show the click.
- **Event log:** one line per event; show `reason.text` in a quieter style, so the judge sees *why* before *what*.
- **Claim board:** a card per claim from `claims.queued`; it shows "testing" after `claim.started` and flips to its verdict on `verdict`.
- **Meter:** elapsed time from `at`, actions from `run.finished.actions`, spend from the sum of `run.finished.cost_usd`.
- **Replay:** the same events from `live_events`, played back with their timestamps.
- Never show a "broken" badge before the `verdict` event: until then a claim is only "testing".
