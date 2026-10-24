# Evaluation: shelfmate

Run on 2026-10-24 16:58 UTC. 2 runs.

**Result: FAIL**

## Checks

- PASS: every run finished
- FAIL: no wrong verdicts
- FAIL: every claim steady (same verdict in 2 of 2 runs)
- FAIL: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 0 of 18 (0.0%)
- Wrong verdicts: 1
- Could not test / no result (never a wrong answer): 17
- TalNex score per run (out of 100): [0.0] (spread 0.0)
- Red flags per run: [0, 0]
- Seconds per run: [324, 183]
- Cost per run (US dollars): [0.0138, 0.0149]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Create an account with an email and a password | works | broken, could_not_test | NO | [0.0] |
| Sign in and sign out | works | could_not_test, could_not_test | yes | [] |
| Add a book with a title and an author | works | could_not_test, could_not_test | yes | [] |
| See your books and search them by title or author | works | could_not_test, could_not_test | yes | [] |
| Edit a book's details or delete it | works | could_not_test, could_not_test | yes | [] |
| Mark a book as Want to read, Reading or Finished and its badge changes | works | could_not_test, could_not_test | yes | [] |
| Rate finished books from 1 to 5 and see the average rating | works | could_not_test, could_not_test | yes | [] |
| Export the shelf as a CSV file | broken or partly_works | could_not_test, could_not_test | yes | [] |
| Set a yearly reading goal and a progress bar shows how many books are … | broken or partly_works | could_not_test, could_not_test | yes | [] |
