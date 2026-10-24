# Evaluation: every planted app

Run on 2026-10-24 16:20 UTC.

**Gate: FAIL**

| App | Result | Right | Wrong | Could not test | Seconds per run | Cost per run (USD) |
|---|---|---|---|---|---|---|
| copier_trickster | FAIL | 18 of 24 | 0 | 6 | [712, 570, 736] | [0.0587, 0.0508, 0.0864] |
| fake_claim | FAIL | 16 of 18 | 1 | 1 | [375, 408, 564] | [0.0347, 0.0328, 0.0334] |
| honest | FAIL | 21 of 24 | 0 | 3 | [582, 570, 793] | [0.0553, 0.068, 0.0974] |
| partly_works | FAIL | 10 of 15 | 0 | 5 | [528, 366, 670] | [0.0377, 0.0298, 0.0402] |
| shelfmate | FAIL | 2 of 27 | 1 | 24 | [174, 297, 459] | [0.0183, 0.0129, 0.0187] |

## Wrong verdicts

- fake_claim: The About page explains what CaptionIt is (expected works, got works, broken, works)
- shelfmate: Create an account with an email and a password (expected works, got works, works, broken)
