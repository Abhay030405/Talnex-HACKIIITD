# Evaluation: task_api

Run on 2026-10-24 19:17 UTC. 3 runs. Baseline on repo-only planted app (sandbox track)

**Result: FAIL**

## Checks

- PASS: every run finished
- FAIL: no wrong verdicts
- FAIL: every claim steady (same verdict in 2 of 3 runs)
- FAIL: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 18 of 27 (66.7%)
- Wrong verdicts: 4
- Could not test / no result (never a wrong answer): 5
- TalNex score per run (out of 100): [] (spread 0.0)
- Red flags per run: [0, 0, 0]
- Seconds per run: [138, 246, 102]
- Cost per run (US dollars): [0.0, 0.0, 0.0]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| GET /health returns status ok | works | works, works, works | yes | [] |
| POST /tasks creates a task and refuses a missing title with 400 | works | works, works, works | yes | [] |
| POST /tasks refuses a priority that is not a whole number from 1 to 5 … | broken | broken, broken, could_not_test | yes | [] |
| GET /tasks lists tasks, filters with ?done=true or false and sorts by … | works | works, works, works | yes | [] |
| GET /tasks/<id> returns one task or 404 | works | works, works, works | yes | [] |
| PATCH /tasks/<id> renames a task and refuses an empty title with 400 | works | works, works, works | yes | [] |
| POST /tasks/<id>/complete marks a task done and answers 404 for an unk… | works | works, partly_works, partly_works | yes | [] |
| DELETE /tasks/<id> answers 404 for an id that does not exist | broken | could_not_test, could_not_test, could_not_test | yes | [] |
| GET /stats returns the correct total, done and open counts | broken | partly_works, works, could_not_test | NO | [] |
