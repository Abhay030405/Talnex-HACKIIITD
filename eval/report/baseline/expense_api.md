# Evaluation: expense_api

Run on 2026-10-24 19:14 UTC. 3 runs. Baseline on repo-only planted app (sandbox track)

**Result: FAIL**

## Checks

- PASS: every run finished
- FAIL: no wrong verdicts
- PASS: every claim steady (same verdict in 2 of 3 runs)
- FAIL: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 21 of 27 (77.8%)
- Wrong verdicts: 2
- Could not test / no result (never a wrong answer): 4
- TalNex score per run (out of 100): [] (spread 0.0)
- Red flags per run: [0, 0, 0]
- Seconds per run: [111, 123, 96]
- Cost per run (US dollars): [0.0, 0.0, 0.0]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| GET /health returns status ok | works | works, works, works | yes | [] |
| POST /expenses refuses an amount that is not a positive number with 40… | broken | could_not_test, could_not_test, could_not_test | yes | [] |
| POST /expenses records an expense with an amount and a category and re… | works | works, works, works | yes | [] |
| GET /expenses lists expenses newest first and supports ?category= and … | works | works, works, works | yes | [] |
| GET /expenses/:id returns one expense or 404 | works | works, works, works | yes | [] |
| DELETE /expenses/:id removes an expense and answers 404 for an unknown… | works | works, works, works | yes | [] |
| PATCH /expenses/:id changes the note or the category of an expense | works | works, works, works | yes | [] |
| GET /expenses/summary returns the total spent and the correct total fo… | broken | works, works, could_not_test | yes | [] |
| GET /expenses/export returns all expenses as CSV with a header row | works | works, works, works | yes | [] |
