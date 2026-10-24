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

## How we split the harness: two layers, one engine

The harness has two layers, and each of us owns one, so we never edit the same file:

- **Judging (Arnav):** how a claim becomes checks, how the two judges mark them, how the verdict is decided, and
  the never-blame ladder. This decides **whether TalNex is right**.
- **Acting (Abhay):** how the agent actually uses the browser: the step loop, the actions, finding elements, what
  it sees of the page, sessions, speed and cost. This decides **whether TalNex manages to do the test**, and how
  fast and cheaply.

Most of our remaining wrong or unconfirmed results are acting problems, not judging problems:
- the agent never typed the bad input it was meant to test;
- it ran out of time on a long sign-up;
- a click hit the wrong element;
- a long answer failed a step.

Every saved second or call is also a saving on every claim of every event. So the acting layer is where the next
big gains are.

| Arnav: judging layer | Abhay: acting layer |
|---|---|
| `testing/planner/`, `testing/checks.py`, `testing/scope.py` | `testing/runner/executor.py` (the step loop) |
| `testing/runner/judge.py` (the run's final look) | `testing/runner/actions.py`, `testing/runner/driver.py` |
| `testing/proof_check/`, `testing/retries/` | `testing/runner/runner.py` (sessions, tries, cost) |
| `scoring/claim_points/` | `llm/prompts/runner.py`: `STEP_SYSTEM` and `step_user` only |
| `llm/prompts/test_planner.py`, `proof_checker.py`, and `FINAL_*` in `runner.py` | `tinyfish/` browser sessions, if a task needs it |

- **Shared, changed only through a PR both of us review:** `formats/` (`Check`, `TestPlan`, `StepRecord`),
  `worker/evaluate.py` (the gate) and `eval/expected/`.
- **The line between the layers** is `judge.final_look(...)`. The step loop hands over what was done and the final
  page; the judge hands back the outcome. Change it only by agreement.
- If you need a change on the other side, ask; don't edit it on your branch.

## Your tasks (acting layer)

**Every task is measured with the gate.** Verdicts must stay as good or get better, never worse. The gate's summary
already shows seconds and dollars per run, so put the before and after numbers in each PR. A change that saves time
but loses a correct verdict doesn't merge.

1. **Do simple steps without the model.**
   - Many plan steps name one clear action ("type 'milk' into 'What needs to be done?'", "click Add", "press
     Enter"). Turn those into actions directly with the browser library's locators (by label, placeholder, role and
     name), and only ask the model when that fails or the step is not simple.
   - Expect far fewer model calls per claim (we measured about 23 per claim, about 2.8 s each). Keep a screenshot
     after every action, exactly as now.
2. **Send a smaller page snapshot each turn.**
   - Today every turn resends up to `RUNNER_SNAPSHOT_CHARS` of the accessibility tree: about 1,700 input tokens per
     call, roughly 25 tokens in for each token out.
   - Send the interactive elements (buttons, inputs, links) plus what changed since the last turn. Input tokens are
     most of the model cost.
3. **Put the fixed part of each prompt first.** Order the step prompt as rules, then plan, then claim, then
   history, then the page, so providers that cache repeated prompt starts can do it. Check whether our Azure
   deployment reports cached tokens, and log them to `usage_log`.
4. **Reuse one browser session across a claim's tries and extra tests.** One demo run opened 12 sessions for
   7 claims. Each opening costs start-up time and billed minutes.
5. **Make actions more reliable:**
   - find elements when the name differs slightly;
   - wait for the page to settle after an action (network idle, not a fixed 400 ms);
   - handle pop-up dialogs, new tabs and cookie banners;
   - spot a click that did nothing, and tell the model.

   Each of these is a "could not test" we lose today.
6. **Remember what worked on a site (later).** Save the action sequence that got past a sign-up or reached a
   feature, and replay it first on the next run; ask the model only when the page has changed. This needs a table,
   and the schema is Go's (Ayush), so plan it with him through a migration.

## Also useful, but second

- The **sandbox track** (`sandbox/api_tests`) still judges each claim as a whole. Giving its plans checks and its
  HTTP proof check per-check marks would bring the new judging to backend tests too. The ladder already accepts
  `parts` on any runner's records.
- **More planted apps** with new claim shapes (form rules, a file download, two users, pages and filters, a wizard),
  with two kept back and used only to test. They don't change the harness, but they prove it generalises.

## Where to start

- Wait for Arnav's message that the round-3 gate is done and `ai/eval-gate` is merged into `main`.
- Then branch from `main`: `ai/model-free-steps` for task 1, and so on. Keep one or two branches open at most.
- Before each merge, run the Python tests and the gate. Write each finding as a test first, as AGENTS.md says.
- Local test setup:
  - the Python tests need `TALNEX_TEST_DATABASE_URL` (a throwaway Postgres with the migrations applied) and,
    for storage tests, `TALNEX_TEST_S3_*`;
  - the Go tests need Go 1.27, or `golang:1.27-alpine` in Docker.
