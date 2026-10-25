# Evaluation: login_guest_2

Run on 2026-10-24 20:00 UTC. 2 runs. Baseline: login lab, before any login fixes

**Result: FAIL**

## Checks

- PASS: every run finished
- PASS: no wrong verdicts
- FAIL: every claim steady (same verdict in 2 of 2 runs)
- FAIL: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 6 of 8 (75.0%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 2
- TalNex score per run (out of 100): [100.0, 100.0] (spread 0.0)
- Red flags per run: [0, 0]
- Seconds per run: [264, 192]
- Cost per run (US dollars): [0.0128, 0.0118]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Use the app as a guest without creating an account | works | works, could_not_test | NO | [10.0] |
| Add a note with a title and see it in the list | works | works, works | yes | [10.0, 10.0] |
| Notes are still in the list after the page is reloaded | works | works, works | yes | [10.0, 10.0] |
| Leave guest mode and be taken back to the start screen | works | could_not_test, works | NO | [10.0] |
