# Evaluation: every planted app

Run on 2026-10-24 20:14 UTC. Baseline: login lab, before any login fixes

**Gate: FAIL**

| App | Result | Right | Wrong | Could not test | Seconds per run | Cost per run (USD) |
|---|---|---|---|---|---|---|
| login_pw_1 | FAIL | 2 of 8 | 0 | 6 | [87, 105] | [0.0057, 0.0057] |
| login_pw_2 | FAIL | 2 of 8 | 0 | 6 | [102, 105] | [0.0066, 0.0056] |
| login_pw_3 | FAIL | 2 of 8 | 0 | 6 | [123, 123] | [0.006, 0.0056] |
| login_pw_4 | FAIL | 1 of 8 | 1 | 6 | [330, 147] | [0.0098, 0.0069] |

## Wrong verdicts

- login_pw_4: Create an account with an email and a password and reach the notes page (expected works, got broken, works)
