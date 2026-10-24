# TalNex — Implementation Plan

Recruiter side first, hackathon side next, sandbox (VM) last. Everything in the "shared" column is built **once**, with no recruiter-only or hackathon-only assumptions, so the hackathon side reuses it as-is.

Source of truth for what each part does: `docs/talnex_architecture.md`.

---

## 1. What is shared and what is mode-specific

| Part | Shared by recruiter + hackathon + sandbox | Mode-specific |
|---|---|---|
| Settings, Docker Compose, Postgres, `migrate` | ✔ | — |
| Database schema (all tables in architecture §20 are created up front) | ✔ | — |
| Job queue (`jobs` table, wake-up signal, retries, next stage in the same step) | ✔ | Stage order per mode lives in `backend/internal/pipeline/` |
| Go API skeleton, owner checks, Auth.js hand-off | ✔ | Routes for events vs candidates |
| R2 / S3 storage (RustFS locally) and short-lived view links | ✔ | — |
| OpenRouter client, model roles, `usage_log` | ✔ | — |
| TinyFish client (fetch, agent, browser, search, vault) | ✔ | — |
| Safety (site rules, run limits, hidden-instruction check) | ✔ | — |
| Claims → test planner → runner → proof check → never-blame → results | ✔ | Where claims come from (video / criteria / resume + README) |
| Login ladder (steps 2–6; step 1 is the hackathon form login) | ✔ | Phone OTP source differs (test number vs team SIM) |
| GitHub data (Go) | ✔ | — |
| Repo vs live, tutorial copy, hidden instructions | ✔ | — |
| Flags (levels, evidence) | ✔ | — |
| Proof card components (claim rows, step viewer, flag badges) | ✔ | Report layout differs |
| Scoring engine (verdict → points, group score, coverage, confidence) | ✔ built generic | Used in hackathon; recruiter shows no score |
| Resume reader, coding profiles (Codeforces / LeetCode / CodeChef), recruiter report, resume cleanup | — | Recruiter only |
| Video reader, event dates check, sponsor check, copy between teams, feature comparison, AI opinion | — | Hackathon only |
| sandboxd + `ai/talnex_ai/sandbox/` | ✔ | Built last |

## 2. Design rules that keep shared parts shared

1. **A "subject" is either a project or a candidate project.** Claims, test runs, results and flags point to it through the same shape (`claims` already references either). No code asks "is this recruiter?" except the pipeline order and the report.
2. **The pipeline is data.** `backend/internal/pipeline/` holds an ordered list of stages per mode. Python stage handlers never decide what comes next; Go/queue does.
3. **The test engine takes a runner.** Live agent runner now, sandbox HTTP runner later. Planner, proof check, verdicts and scoring never know which runner ran.
4. **Step records are generic** (`kind` = screen / http / command, plus a proof key).
5. **Claim groups are data.** Adding Setup or Edge cases later is a new value, not new code.
6. **Scoring is a pure function** of claims and results, with no mode inside it.
7. **Every outside service has one client folder** (`tinyfish/`, `llm/openrouter/`, `sandbox/client/`, R2 under `storage/`).

## 3. Build order

Each phase ends with something that runs and is tested. Merge a feature branch only when its phase item works.

### Phase 0 — Foundations (shared)
1. `.env.example`, settings modules for Go, Python and web; `docker-compose.yml` with `postgres`, `s3`, `migrate`, `api`, `go-worker`, `ai-worker`.
2. Go migrations for **every table** in architecture §20 (so Python and web never wait on schema).
3. `jobs` queue in Go: add, take with a lock, wake-up signal, retry, time limit, next stage in the same database step. Go and Python worker skeletons that take a no-op job end to end.
4. Go API skeleton: health, owner checks, event/candidate create stubs.
5. R2/S3 storage helper in Go and Python.
6. OpenRouter client with retries, low-temperature default, and `usage_log` on every call.
7. `/healthz` for each service; `docker compose up --build` brings everything up.

**Status: done.** Built and tested: compose with `postgres`, `s3` (RustFS), `migrate`, `api`, `go-worker`, `ai-worker`; migrations 1–7 (all tables, role level, candidate-level scores, queue functions); the queue (Postgres functions shared by Go and Python); Go API with signed-token auth and owner checks; storage helpers in Go and Python; OpenRouter client with retries and `usage_log`; `/healthz` on every service. The self-test pipeline (Python → Go → Python) runs across the three containers in under a second.

The website is built too: calm honey-yellow theme in `globals.css` (light and dark), landing page, Auth.js sign-in (Google when keys are set, email-only for local work), dashboard, new hackathon and recruiter forms, event and candidate pages. Tests enforce the design rules (no inline styles, colours or fonts outside `globals.css`; settings only in `lib/env.ts`).

**Still open:** Google sign-in keys (`GOOGLE_CLIENT_ID/SECRET`); models for the image-reading roles (video reader, proof checker, the two opinion models); production R2 and Postgres settings (when deploying).

**Done when:** a dummy job travels Go API → queue → Python worker → result row, and appears in `usage_log`.

### Phase 1 — Shared testing engine (live track)
**Detailed plan: `docs/phase1/01_plan.md`** (TinyFish spike first, then 12 items; the items that need no TinyFish are built first).

1. TinyFish client: fetch, agent run, vault read. Run-limit and "TalNex test" labelling in `safety/site_rules`.
2. Claims format and claim storage.
3. Test planner (all test types), with prompt files under `llm/prompts/`.
4. Runner: executes a plan through TinyFish, saves a step record and screenshot per step.
5. Proof checker (an independent call) and the never-blame ladder in `testing/retries`.
6. Result + confidence writing.
7. Login ladder steps 2–4 (guest/demo, AgentMail email, Gmail plus-address). Steps 5–6 later in the recruiter phase.

**Done when:** a hand-typed claim against a known live site gives a correct verdict with screenshots and a second-model check.

### Phase 2 — Recruiter pipeline (core)
1. `resume/` reader (pdfplumber + model) → candidate projects, links, handles.
2. Recruiter form + upload in the web app; Go API creates the candidate and the first job.
3. Precheck (fetch live link and repo).
4. Claims from resume bullets + README; "can't test by use" marking.
5. Go GitHub data (repo info, dates, files).
6. Wire stages into the recruiter pipeline order; status updates reach the web page.

**Done when:** uploading the test resume produces claims and live results for its projects.

### Phase 3 — Originality and signals (recruiter)
1. Repo vs live site; tutorial copy (TinyFish Search + comparison). **Shared with hackathon.**
2. Flags collection with levels. **Shared.**
3. Codeforces in Go (all-skipped contests, practice removed).
4. LeetCode capture and paste analysis (TinyFish browser + Vault), then CodeChef.
5. Login ladder steps 5–6 for recruiter: team SIM + SMS forwarder, AgentCall backup, plus Google/GitHub saved sessions.

### Phase 4 — Recruiter report and privacy
1. Recruiter proof report generator (no score; time saved).
2. Web pages: proof report, claim rows, step screenshot viewer, flag badges (build the components generic).
3. Resume + personal-data cleanup job (Go) and R2 delete.
4. Owner-only access checks across every read route.

**Done when:** the full recruiter flow runs on the test resume, and the resume file is gone after the report.

### Phase 5 — Planted apps and evaluation
1. Build the planted apps and expected results in `testdata/planted/` and `eval/expected/`.
2. Repeat-run harness (3 runs per app) and the report in `eval/report/`.
3. Fix issues found; every real failure becomes a test case.

### Phase 6 — Hackathon side (reuses everything above)
Only hackathon-specific parts remain: event + criteria forms, video reader, claims from video + criteria, Demo Replay, event-date and sponsor checks, scoring groups UI, copy between teams, feature comparison, AI opinion, event dashboard, re-run. The scoring engine from Phase 1 is wired in here.

### Phase 7 — Sandbox / VM track (last)
1. `sandboxd` with the **docker** driver: create, upload, exec, ports, destroy, health, token auth, reaper.
2. Base images (`node`, `python`, `go`, `java`, `compose`).
3. `ai/talnex_ai/sandbox/client/` and the `sandbox_runs` records.
4. Stack detect → run recipe → build and start with the one-fix rule.
5. Route discovery.
6. API tests (normal, known-answer, edge, repeat, light load, access) using the existing planner and a new HTTP runner.
7. Repo's own tests; code review ("reviewed from code, not run").
8. Setup and Edge-case groups wired into scoring (data only) and into the recruiter report counts.
9. Planted `backend_only_repo` and evaluation.
10. Later: Firecracker driver and isolation hardening (architecture 28.13).

### Phase 8 — Authorship proof (both modes)
Architecture section 30. Built after the sandbox track so code locate can reuse route discovery; it still works without a sandbox run.
1. Go migration: `authorship` table and optional team GitHub handles on `projects`.
2. Go `github/`: blame (GraphQL) and commits per file (REST) with push times, cached by repo and commit; the `github_history` job (A2).
3. Python `checks/authorship/`: code locate (A1) from route mapping, then tree-sitter, then a model; the same removal list as the copy detector.
4. Python authorship read (A3): shares, build pattern, arrival; the "new, moved or reformatted" model call; could-not-trace reasons.
5. Authorship flags through the shared flags collector (section 30.8).
6. Stages A1–A3 added to the hackathon and recruiter pipelines.
7. Web: authorship line per claim row, team "who built what" table, team handles field on the hackathon form.
8. Planted `team_project`, the extra feature in `built_before_event`, expected results and repeat runs.

**Done when:** the planted apps show the authorship answers in architecture 30.12, and the honest app shows none of the authorship flags.

### Phase 9 — Voice walkthrough (both modes)
Architecture section 31. Built after Phase 8, since answers use the code map and authorship.
1. Go migration: `walkthroughs` table.
2. Go `results/`: ask and read routes with owner checks; audio upload to R2; the `walkthrough_answer` job.
3. Python `reports/walkthrough/`: speech to text (faster-whisper) and audio delete; pick the feature; gather evidence.
4. Answer writer: prompt `llm/prompts/walkthrough.py`, low temperature; plain-code check that drops sentences without real proof; hidden-instruction reporting.
5. Web: "Ask about this feature" box with microphone, code highlight, proof links, read aloud with browser speech.
6. Planted-app questions from architecture 31.7, with expected answers in `eval/expected/`, and repeat runs.

**Done when:** the questions in architecture 31.7 get the expected answers, every proof link opens real evidence, and nothing listed as missing is present in the code.

## 4. How I start (first working session)

1. Fix the open details in `AGENTS.md` (commands, branch names) so the repo is ready.
2. Phase 0 steps 1–2 on one branch `backend/foundations`: env, compose, migrations for all tables. Hand over for review before starting the queue.
3. Then the queue and worker skeletons, then the OpenRouter client.

Each step is small, runs on its own and gets a test before the branch is merged.

### Phase 9 — Guided tour walkthrough (both modes)
Architecture section 32. Builds on the sandbox track (code VM), the live events stream and the runner. One branch per part, in this order:
1. `ai/tour-guide`: the code-only VM mode, the three read tools, the guide agent, the tour plan and its check, the driver, the `tour_message` handler. Tested with scripted models and a fake VM.
2. `backend/tour-sessions`: migration for `tour_sessions` and `tour_messages`, the Go endpoints and the daily limit, the `tour_session` live subject.
3. `web/walkthrough`: the two-panel page and its components.
4. Check with the planted apps (32.7).
