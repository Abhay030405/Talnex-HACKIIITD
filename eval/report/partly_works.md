# Evaluation: partly_works

Run on 2026-10-24 16:12 UTC. 3 runs.

**Result: FAIL**

## Checks

- PASS: every run finished
- PASS: no wrong verdicts
- PASS: every claim steady (same verdict in 2 of 3 runs)
- FAIL: majority verdict is the expected one for every claim
- FAIL: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 10 of 15 (66.7%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 5
- TalNex score per run (out of 100): [50.0, 75.0, 38.0] (spread 37.0)
- Red flags per run: [0, 0, 0]
- Seconds per run: [528, 366, 670]
- Cost per run (US dollars): [0.0377, 0.0298, 0.0402]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Add a note with a title and see it in the list | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Type in the search box and the list narrows to the matching notes | works | could_not_test, works, could_not_test | yes | [] |
| Pin a note so it moves to the top of the list with a Pinned label | broken | broken, could_not_test, broken | yes | [0.0, 0.0] |
| Adding a note with an empty title shows a clear message and adds nothi… | broken | could_not_test, could_not_test, broken | yes | [0.0] |
| Export the notes as a PDF file (control) | broken | broken, broken, broken | yes | [0.0, 0.0, 0.0] |
