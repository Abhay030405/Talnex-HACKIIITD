# Evaluation: every planted app

Run on 2026-10-24 17:37 UTC. email sign-up on (new EMAIL_LOGIN_SECRET)

**Gate: FAIL**

> **Note (shelfmate):** this machine's `EMAIL_LOGIN_SECRET` was newly generated, so the per-site password does not match the shelfmate account that earlier runs created with the team inbox. Sign-in fails and every later claim is "could not test". This is a setup mismatch, not a TalNex result: re-run with the team's shared secret. The other four apps: 24 of 27 right, 0 wrong.

| App | Result | Right | Wrong | Could not test | Seconds per run | Cost per run (USD) |
|---|---|---|---|---|---|---|
| copier_trickster | FAIL | 7 of 8 | 0 | 1 | [472] | [0.0389] |
| fake_claim | FAIL | 5 of 6 | 0 | 1 | [333] | [0.0268] |
| honest | PASS | 8 of 8 | 0 | 0 | [499] | [0.0441] |
| partly_works | FAIL | 4 of 5 | 0 | 1 | [670] | [0.0396] |
| shelfmate | FAIL | 0 of 9 | 1 | 8 | [658] | [0.066] |

## Wrong verdicts

- shelfmate: Create an account with an email and a password (expected works, got broken)
