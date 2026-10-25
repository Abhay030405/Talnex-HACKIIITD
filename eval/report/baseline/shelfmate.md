# Evaluation: shelfmate

Run on 2026-10-24 19:25 UTC. 3 runs. Baseline on rebuilt live apps, no login claims

**Result: FAIL**

## Checks

- PASS: every run finished
- FAIL: no wrong verdicts
- FAIL: every claim steady (same verdict in 2 of 3 runs)
- FAIL: majority verdict is the expected one for every claim
- FAIL: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 15 of 24 (62.5%)
- Wrong verdicts: 2
- Could not test / no result (never a wrong answer): 7
- TalNex score per run (out of 100): [95.0, 85.0, 79.0] (spread 16.0)
- Red flags per run: [0, 0, 0]
- Seconds per run: [408, 405, 528]
- Cost per run (US dollars): [0.0443, 0.044, 0.0597]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| Add a book with a title and an author and it appears on the shelf | works | works, works, works | yes | [10.0, 10.0, 9.3] |
| Search the shelf by title or author and the list narrows to the matchi… | works | could_not_test, could_not_test, works | yes | [10.0] |
| Edit a book's title or author, or delete the book | works | could_not_test, could_not_test, partly_works | yes | [5.0] |
| Mark a book as Want to read, Reading or Finished and its badge changes | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Rate finished books from 1 to 5 stars and see the average rating | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Filter the shelf by status with the All, Want to read, Reading and Fin… | works | works, partly_works, could_not_test | NO | [10.0, 5.0] |
| Export the shelf as a CSV file | broken or partly_works | could_not_test, could_not_test, broken | yes | [0.0] |
| Set a yearly reading goal and a progress bar shows how many books are … | broken or partly_works | partly_works, partly_works, partly_works | yes | [5.0, 5.0, 5.0] |
