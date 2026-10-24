# Evaluation: shelfmate

Run on 2026-10-24 15:15 UTC. 3 runs. round 3: promises vs steps, fresh visitor, time per step, trimmed text

**Result: FAIL**

## Checks

- PASS: every run finished
- FAIL: no wrong verdicts
- PASS: every claim steady (same verdict in 2 of 3 runs)
- FAIL: majority verdict is the expected one for every claim
- FAIL: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 20 of 27 (74.1%)
- Wrong verdicts: 1
- Could not test / no result (never a wrong answer): 6
- TalNex score per run (out of 100): [80.0, 92.0, 84.0] (spread 12.0)
- Red flags per run: [0, 0, 0]
- Seconds per run: [634, 763, 519]
- Cost per run (US dollars): [0.2815, 0.315, 0.2376]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Create an account with an email and a password | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Sign in and sign out | works | could_not_test, works, works | yes | [10.0, 10.0] |
| Add a book with a title and an author | works | works, works, works | yes | [7.7, 10.0, 7.7] |
| See your books and search them by title or author | works | could_not_test, works, works | yes | [10.0, 10.0] |
| Edit a book's details or delete it | works | could_not_test, could_not_test, partly_works | yes | [5.0] |
| Mark a book as Want to read, Reading or Finished and its badge changes | works | works, could_not_test, works | yes | [10.0, 10.0] |
| Rate finished books from 1 to 5 and see the average rating | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Export the shelf as a CSV file | broken or partly_works | broken, broken, partly_works | yes | [0.0, 0.0, 5.0] |
| Set a yearly reading goal and a progress bar shows how many books are … | broken or partly_works | partly_works, could_not_test, partly_works | yes | [5.0, 5.0] |
