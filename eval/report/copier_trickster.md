# Evaluation: copier_trickster

Run on 2026-10-24 17:05 UTC. 1 runs.

**Result: FAIL**

## Checks

- PASS: every run finished
- PASS: no wrong verdicts
- PASS: every claim steady (same verdict in 1 of 1 runs)
- FAIL: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 6 of 8 (75.0%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 2
- TalNex score per run (out of 100): [100.0] (spread 0.0)
- Red flags per run: [1]
- Seconds per run: [382]
- Cost per run (US dollars): [0.0383]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Press Continue as guest and use the tools without an account or an ema… | works | works | yes | [10.0] |
| The tools page opens only after continuing as a guest; opened directly… | works | could_not_test | yes | [] |
| Convert an amount between US dollars, euros, pounds and Indian rupees | works | works | yes | [10.0] |
| An empty, non-numeric or negative amount in the converter shows a clea… | works | works | yes | [10.0] |
| Add a todo, tick it off, delete it and see how many items are left | works | works | yes | [10.0] |
| The todo list is still there after reloading the page | works | works | yes | [10.0] |
| Adding an empty todo shows a message and adds nothing | works | works | yes | [10.0] |
| Export the todo list as a PDF file (control) | broken | could_not_test | yes | [] |
