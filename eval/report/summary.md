# Evaluation: every planted app

Run on 2026-10-24 17:07 UTC.

**Gate: FAIL**

| App | Result | Right | Wrong | Could not test | Seconds per run | Cost per run (USD) |
|---|---|---|---|---|---|---|
| copier_trickster | FAIL | 6 of 8 | 0 | 2 | [382] | [0.0383] |
| fake_claim | FAIL | 4 of 6 | 0 | 2 | [330] | [0.0243] |
| honest | FAIL | 7 of 8 | 0 | 1 | [442] | [0.0441] |
| partly_works | FAIL | 2 of 5 | 0 | 3 | [460] | [0.024] |
| shelfmate | FAIL | 0 of 9 | 1 | 8 | [288] | [0.0158] |

## Wrong verdicts

- shelfmate: Create an account with an email and a password (expected works, got broken)
