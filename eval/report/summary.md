# Evaluation: every planted app

Run on 2026-10-24 15:15 UTC. round 3: promises vs steps, fresh visitor, time per step, trimmed text

**Gate: FAIL**

| App | Result | Right | Wrong | Could not test | Seconds per run | Cost per run (USD) |
|---|---|---|---|---|---|---|
| copier_trickster | PASS | 23 of 24 | 0 | 1 | [549, 486, 444] | [0.1363, 0.1531, 0.1465] |
| fake_claim | FAIL | 13 of 18 | 0 | 5 | [429, 315, 261] | [0.0817, 0.0791, 0.0808] |
| honest | PASS | 23 of 24 | 0 | 1 | [664, 489, 402] | [0.1543, 0.167, 0.1449] |
| partly_works | FAIL | 11 of 15 | 0 | 4 | [423, 513, 438] | [0.126, 0.0941, 0.0984] |
| shelfmate | FAIL | 20 of 27 | 1 | 6 | [634, 763, 519] | [0.2815, 0.315, 0.2376] |

## Wrong verdicts

- shelfmate: Edit a book's details or delete it (expected works, got could_not_test, could_not_test, partly_works)
