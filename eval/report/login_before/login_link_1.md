# Evaluation: login_link_1

Run on 2026-10-25 02:54 UTC. 2 runs. Baseline: login lab, before any login fixes

**Result: FAIL**

## Checks

- FAIL: every run finished
- PASS: no wrong verdicts
- FAIL: every claim steady (same verdict in 2 of 2 runs)
- FAIL: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 0 of 8 (0.0%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 8
- TalNex score per run (out of 100): [] (spread 0.0)
- Red flags per run: [0, 0]
- Seconds per run: [17338, 500]
- Cost per run (US dollars): [0.0, 0.0065]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Sign up with an email and confirm it with the link that is emailed to … | works | None, could_not_test | NO | [] |
| Add a note with a title and see it in the list | works | None, could_not_test | NO | [] |
| Notes are still in the list after the page is reloaded | works | None, could_not_test | NO | [] |
| Sign out and be taken back to the start screen | works | None, could_not_test | NO | [] |
