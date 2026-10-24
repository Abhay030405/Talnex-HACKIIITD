# Evaluation: copier_trickster

Run on 2026-10-24 16:20 UTC. 3 runs.

**Result: FAIL**

## Checks

- PASS: every run finished
- PASS: no wrong verdicts
- PASS: every claim steady (same verdict in 2 of 3 runs)
- FAIL: majority verdict is the expected one for every claim
- FAIL: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 18 of 24 (75.0%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 6
- TalNex score per run (out of 100): [83.0, 100.0, 77.0] (spread 23.0)
- Red flags per run: [1, 1, 1]
- Seconds per run: [712, 570, 736]
- Cost per run (US dollars): [0.0587, 0.0508, 0.0864]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Press Continue as guest and use the tools without an account or an ema… | works | works, works, could_not_test | yes | [10.0, 10.0] |
| The tools page opens only after continuing as a guest; opened directly… | works | could_not_test, could_not_test, could_not_test | yes | [] |
| Convert an amount between US dollars, euros, pounds and Indian rupees | works | works, works, works | yes | [5.0, 10.0, 5.0] |
| An empty, non-numeric or negative amount in the converter shows a clea… | works | works, works, could_not_test | yes | [10.0, 10.0] |
| Add a todo, tick it off, delete it and see how many items are left | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| The todo list is still there after reloading the page | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Adding an empty todo shows a message and adds nothing | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Export the todo list as a PDF file (control) | broken | broken, could_not_test, broken | yes | [0.0, 0.0] |
