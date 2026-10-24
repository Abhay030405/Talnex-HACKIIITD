# Evaluation: partly_works

Run on 2026-10-24 15:06 UTC. 3 runs. round 3: promises vs steps, fresh visitor, time per step, trimmed text

**Result: FAIL**

## Checks

- PASS: every run finished
- PASS: no wrong verdicts
- PASS: every claim steady (same verdict in 2 of 3 runs)
- FAIL: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 11 of 15 (73.3%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 4
- TalNex score per run (out of 100): [56.0, 56.0, 50.0] (spread 6.0)
- Red flags per run: [0, 0, 0]
- Seconds per run: [423, 513, 438]
- Cost per run (US dollars): [0.126, 0.0941, 0.0984]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Add a note with a title and see it in the list | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Type in the search box and the list narrows to the matching notes | works | works, works, could_not_test | yes | [10.0, 10.0] |
| Pin a note so it moves to the top of the list with a Pinned label | broken | broken, broken, could_not_test | yes | [0.0, 0.0] |
| Adding a note with an empty title shows a clear message and adds nothi… | broken | broken, broken, broken | yes | [0.0, 0.0, 0.0] |
| Export the notes as a PDF file (control) | broken | could_not_test, could_not_test, broken | yes | [0.0] |
