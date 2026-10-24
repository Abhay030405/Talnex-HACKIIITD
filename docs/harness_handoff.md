# Harness handoff: for Abhay (and Abhay's Claude)

Written 2026-10-24 by Arnav's side. Read this whole file before changing anything in the test engine.

## Right now: what Arnav is running (don't disturb it)

- **The rigorous gate is running**: all 5 live planted apps, 3 runs each, on round 3 of the harness redesign.
  Started about 14:45 UTC 2026-10-24 and takes about 45 minutes. Its result decides whether `ai/eval-gate` is merged.
- Until Arnav says it has finished, please **don't**:
  - rebuild or restart the `ai-worker` container (it would kill the runs);
  - start another gate or live run against the same stack (it shares the TinyFish budget and the workers);
  - push to the `ai/eval-gate` branch.
- Reading the code and planning your part is fine. Start your branch after the gate result (see "Where to start").

## Why the harness changed

Real runs on our planted apps gave wrong verdicts on working features, and a few broken ones passed. Every
mistake had the same root: **a model decided in free text what "working" meant, and then gave one overall
verdict.** So:
- plans quietly added requirements the claim never made ("private pages stay blocked when signed out");
- a part beyond the claim, or a step our own agent skipped, turned "works" into "partly works";
- an error page caused by the test's own action was called "blocked";
- a count or progress bar at its starting value (0 of 12) passed as "works".

Patching prompts one by one didn't fix it. The redesign below did, and the gate measures it.

## The design (live-browser track, built by Arnav, on branch `ai/eval-gate`)

1. **A claim is split into checks.** Every main test plan (`normal`, `access`) has 1 to 4 `checks`
   (`formats.Check`). Each check has:
   - `text`: what must be visible;
   - `quote`: the claim's own words it proves, copied from the claim;
   - `promise`: true for what the claim says the visitor **gets**, false for a **step on the way** (open the page,
     choose a photo).

   Plain code (`testing/planner/planner.py: check_parts`) rejects a plan whose quotes are not from the claim or
   leave most of the claim untested, or that has no promise. It uses word overlap (`testing/scope.py`), nothing
   app-specific. Extra tests (`bad_input`, `known_answer`, `repeat`) need no checks.
2. **Both judges mark every check** (`testing/checks.py`): `seen`, `not_seen`, `cant_tell` or `beyond_claim`.
   - The run's final judge (`testing/runner/executor.py`) and the blind screenshot check
     (`testing/proof_check`) each mark the same numbered checks.
   - The run's judge can no longer answer "blocked".
3. **Code decides the verdict** (`scoring/claim_points`: `merge_part`, `outcome_from_parts`, `_decide_parts`):
   - A part is `not_seen` only when **both** judges say so. One judge never blames alone; a contradiction is
     "disputed" and the claim is left unconfirmed.
   - Only **promise** parts decide the result. Every promise seen means works. Some promises not seen means partly
     works. No promise seen and promises confirmed not seen means broken, and only after the never-blame ladder.
     Anything else is could not test.
   - `beyond_claim` parts are left out.
4. **An incomplete test is retried, never marked down** (`testing/retries`): a run that ran out of time or actions,
   or couldn't show a part, gets one more try built a different way. If that is still incomplete, the claim is
   "could not test". If it now fails, the full never-blame ladder still runs before "broken".
5. **Smaller fixes in the same branch:**
   - the "TalNex test" label goes only on free text, never numbers, dates or emails (`safety/site_rules.LABEL_RULE`);
   - the blind check sees one screenshot per plan step (`screens_for_check`);
   - a real CC0 dog photo is in `testdata/known_answers/`, and READMEs can't be uploaded;
   - a `fresh_start` action clears cookies and storage so signed-out behaviour can be tested;
   - the run's time limit grows with the plan (`RUNNER_SECONDS_PER_STEP`);
   - over-long model text is trimmed instead of failing a step.
6. **Old plans and the sandbox track still work.** Plans without checks are judged as a whole, as before. The ladder
   uses `getattr`, so `HttpPlan` and sandbox `RunRecord`s pass through unchanged.

## The gate (the measuring stick for every change)

```
python -m talnex_ai.worker.evaluate --all --runs 3 --project     # every live planted app, side by side
python -m talnex_ai.worker.evaluate --expected eval/expected/honest.json --runs 3 --project   # one app
```

- Expected answers are in `eval/expected/*.json`. A verdict may be a list when more than one is right
  (`["broken", "partly_works"]`).
- Reports go to `eval/report/<app>.md` and `eval/report/summary.md`; raw runs go to `eval/runs/`.
- It checks:
  - no wrong verdicts ("could not test" is never wrong);
  - the same verdict in 2 of 3 runs;
  - the TalNex score moves 10 points or less;
  - no unexpected red flags.
- Run from the host, it needs the `.env` values with `postgres`/`s3` pointed at `localhost`. Never print `.env`.
- **AGENTS.md rule 6: the gate must pass before any change to testing, scoring, flags or prompts is merged.**

Results so far:
- **Before the redesign:** TinyTools 8.6/10 with 2 wrong.
- **Round 2 (checks + verdict from parts), 3 runs:** TinyTools **24 of 24**, no false "works" on any app. What
  remained:
  - CaptionIt's caption claims were "partly" (the upload step worked);
  - a signed-out claim on QuickKit couldn't be tested;
  - ShelfMate timed out on long plans.
- **Round 3** fixes those three and is the run going now.

## Who owns what (so we never edit the same file)

| Arnav (live-browser harness) | Abhay (your part) |
|---|---|
| `testing/planner/`, `testing/runner/`, `testing/proof_check/`, `testing/retries/` | `sandbox/` (all of it, including `api_tests/` and `code_review/`) |
| `testing/checks.py`, `testing/scope.py` | `worker/evaluate.py` |
| `scoring/claim_points/` | `eval/` (expected answers, reports) |
| `llm/prompts/test_planner.py`, `runner.py`, `proof_checker.py` | `testdata/planted/`, and the planted repos |

- **The shared contract** (`formats.Check`, `formats.TestPlan.checks`, `scoring/claim_points` verdict rules,
  `testing/checks.py` marks) changes only through a PR that both of us review.
- If you need a change in Arnav's files, open an issue or ask; don't edit them on your branch.

## Your tasks

1. **Check-based judging for the sandbox track.**
   - Give `sandbox/api_tests` plans (`HttpPlan`) `checks` the same way: quote the claim, mark promises, and validate
     with `testing/scope.check_parts`-style rules.
   - Make the HTTP proof check (`sandbox/api_tests/proof.py`) and the sandbox run return per-check marks
     (`parts`), using `testing/checks.SCALE`, `PartMark` and `read_marks`.
   - The ladder and `decide` already handle parts: put them on the sandbox `RunRecord(..., parts=...)` and
     `ProofCheck(..., parts)`.
   - Done when the sandbox tests pass, the parts show up in sandbox verdict reasons, and the gate (task 3) passes
     on the repo-only apps.
2. **More planted apps, so we don't overfit to five.**
   - Add new apps with claim shapes we don't have yet: form validation with several rules, a file download (CSV or
     PDF), two users who must not see each other's data, a list with pages or filters, a setting that persists, a
     multi-step wizard.
   - Each app has a few features that work, a few that are broken or partly working, and one or two control
     claims it doesn't have.
   - **Keep at least two apps back.** Use them only to test, never while fixing, so we can see whether the harness
     generalises.
   - Deploy them on Vercel, push each to a public repo (Arnav put the current ones at
     `github.com/arnavraj-7/talnex-planted-*`), and add `eval/expected/<app>.json`.
3. **Put the repo-only apps in the gate.** Add the sandbox / open-theme path to `worker/evaluate.py` so
   `backend_only` and `built_before_event` are checked too, and write their expected answers.
   - `built_before_event` needs a repo whose history really predates the event. Use an older repo or a dated
     import that you document in its README; never fake dates on a real person's work.
4. **Steadiness and failure reports.** Extend the gate's summary:
   - which claims flip between runs;
   - which stages and which marks (`cant_tell`, `disputed`) cause most unconfirmed results;
   - cost and time per claim.

   The live events table (`live_events`) and `usage_log` have what you need.
5. **Later:** a different model family for the blind check (the `MODEL_PROOF_CHECKER` role) once Arnav and Ayush
   pick the second model. Measure it with the gate before switching.

## Where to start

- Wait for Arnav's message that the round-3 gate is done and `ai/eval-gate` is merged into `main`.
- Then branch from `main`: `ai/sandbox-checks` for task 1, `eval/more-planted-apps` for task 2, and so on. Keep
  one or two branches open at most.
- Before each merge, run the Python tests and the gate. Write each finding as a test first, as AGENTS.md says.
- Local test setup:
  - the Python tests need `TALNEX_TEST_DATABASE_URL` (a throwaway Postgres with the migrations applied) and,
    for storage tests, `TALNEX_TEST_S3_*`;
  - the Go tests need Go 1.27, or `golang:1.27-alpine` in Docker.
