# Evaluation: partly_works

Run on 2026-10-24 17:37 UTC. 1 runs. email sign-up on (new EMAIL_LOGIN_SECRET)

**Result: FAIL**

## Checks

- PASS: every run finished
- PASS: no wrong verdicts
- PASS: every claim steady (same verdict in 1 of 1 runs)
- FAIL: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 4 of 5 (80.0%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 1
- TalNex score per run (out of 100): [38.0] (spread 0.0)
- Red flags per run: [0]
- Seconds per run: [670]
- Cost per run (US dollars): [0.0396]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Add a note with a title and see it in the list | works | works | yes | [10.0] |
| Type in the search box and the list narrows to the matching notes | works | could_not_test | yes | [] |
| Pin a note so it moves to the top of the list with a Pinned label | broken | broken | yes | [0.0] |
| Adding a note with an empty title shows a clear message and adds nothi… | broken | broken | yes | [0.0] |
| Export the notes as a PDF file (control) | broken | broken | yes | [0.0] |
