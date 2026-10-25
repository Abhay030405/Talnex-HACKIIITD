# Evaluation: backend_only_repo

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

- Verdicts matching the expected answer: 20 of 24 (83.3%)
- Wrong verdicts: 1
- Could not test / no result (never a wrong answer): 3
- TalNex score per run (out of 100): [] (spread 0.0)
- Red flags per run: [0, 0, 0]
- Seconds per run: [123, 108, 102]
- Cost per run (US dollars): [0.0, 0.0, 0.0]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| GET /health returns status ok | works | works, works, works | yes | [] |
| POST /bookmarks saves a bookmark and refuses a missing or invalid url … | works | works, works, works | yes | [] |
| GET /bookmarks lists all bookmarks, newest first | works | works, partly_works, works | yes | [] |
| GET /bookmarks?tag=x lists only bookmarks that have the tag | works | works, works, works | yes | [] |
| GET /bookmarks/:id returns one bookmark or 404 if it does not exist | works | works, works, works | yes | [] |
| DELETE /bookmarks/:id removes a bookmark and answers 404 for an unknow… | works | works, works, works | yes | [] |
| PUT /bookmarks/:id refuses a missing or invalid url or an empty title … | broken | could_not_test, could_not_test, could_not_test | yes | [] |
| POST /bookmarks/import with an empty or malformed body is refused with… | broken | broken, broken, broken | yes | [] |
