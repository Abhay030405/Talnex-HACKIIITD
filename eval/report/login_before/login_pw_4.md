# Evaluation: login_pw_4

Run on 2026-10-24 20:14 UTC. 2 runs. Baseline: login lab, before any login fixes

**Result: FAIL**

## Checks

- PASS: every run finished
- FAIL: no wrong verdicts
- FAIL: every claim steady (same verdict in 2 of 2 runs)
- FAIL: majority verdict is the expected one for every claim
- FAIL: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 1 of 8 (12.5%)
- Wrong verdicts: 1
- Could not test / no result (never a wrong answer): 6
- TalNex score per run (out of 100): [0.0, 100.0] (spread 100.0)
- Red flags per run: [0, 0]
- Seconds per run: [330, 147]
- Cost per run (US dollars): [0.0098, 0.0069]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Create an account with an email and a password and reach the notes pag… | works | broken, works | NO | [0.0, 10.0] |
| Add a note with a title and see it in the list | works | could_not_test, could_not_test | yes | [] |
| Notes are still in the list after the page is reloaded | works | could_not_test, could_not_test | yes | [] |
| Sign out and be taken back to the start screen | works | could_not_test, could_not_test | yes | [] |
