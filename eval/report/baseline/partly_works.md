# Evaluation: partly_works

Run on 2026-10-24 19:26 UTC. 3 runs. Baseline on rebuilt live apps, no login claims

**Result: FAIL**

## Checks

- PASS: every run finished
- FAIL: no wrong verdicts
- PASS: every claim steady (same verdict in 2 of 3 runs)
- FAIL: majority verdict is the expected one for every claim
- FAIL: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 19 of 24 (79.2%)
- Wrong verdicts: 2
- Could not test / no result (never a wrong answer): 3
- TalNex score per run (out of 100): [48.0, 40.0, 58.0] (spread 18.0)
- Red flags per run: [0, 0, 0]
- Seconds per run: [417, 465, 510]
- Cost per run (US dollars): [0.041, 0.0444, 0.0515]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Add a note with a title and see it in the list | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Type in the search box and the list narrows to the matching notes | works | could_not_test, works, works | yes | [10.0] |
| Edit a note's title or text and save the change | works | could_not_test, broken, broken | yes | [0.0, 0.0] |
| Delete a note and it disappears from the list | works | works, works, works | yes | [10.0, 8.5, 10.0] |
| Pin a note so it moves to the top of the list with a Pinned label | broken | broken, broken, could_not_test | yes | [0.0, 0.0] |
| Adding a note with an empty title shows a clear message and adds nothi… | broken | broken, broken, broken | yes | [0.0, 0.0, 0.0] |
| A counter shows how many notes there are and goes down when a note is … | broken or partly_works | partly_works, partly_works, partly_works | yes | [2.5, 5.0, 5.0] |
| Export the notes as a PDF file (control) | broken | broken, broken, broken | yes | [0.0, 0.0, 0.0] |
