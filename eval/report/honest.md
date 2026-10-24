# Evaluation: honest

<<<<<<< HEAD
Run on 2026-10-24 16:18 UTC. 3 runs.
=======
Run on 2026-10-24 17:34 UTC. 1 runs. email sign-up on (new EMAIL_LOGIN_SECRET)
>>>>>>> ai/tour-guide

**Result: FAIL**

## Checks

- PASS: every run finished
- PASS: no wrong verdicts
<<<<<<< HEAD
- PASS: every claim steady (same verdict in 2 of 3 runs)
- FAIL: majority verdict is the expected one for every claim
- FAIL: TalNex score spread within 10 points
=======
- PASS: every claim steady (same verdict in 1 of 1 runs)
- PASS: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
>>>>>>> ai/tour-guide
- PASS: no unexpected red flags

## Numbers

<<<<<<< HEAD
- Verdicts matching the expected answer: 21 of 24 (87.5%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 3
- TalNex score per run (out of 100): [87.0, 89.0, 100.0] (spread 13.0)
- Red flags per run: [0, 0, 0]
- Seconds per run: [582, 570, 793]
- Cost per run (US dollars): [0.0553, 0.068, 0.0974]
=======
- Verdicts matching the expected answer: 8 of 8 (100.0%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 0
- TalNex score per run (out of 100): [89.0] (spread 0.0)
- Red flags per run: [0]
- Seconds per run: [499]
- Cost per run (US dollars): [0.0441]
>>>>>>> ai/tour-guide

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
<<<<<<< HEAD
| Anyone can enter as a guest and use the tools without signing up or gi… | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Once inside as a guest, the page shows both a currency converter and a… | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| The converter changes an amount between US dollars, euros, British pou… | works | could_not_test, works, could_not_test | yes | [10.0] |
| Typing an empty, non-numeric or negative amount into the converter sho… | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| A todo can be added, marked as done and deleted, and the list shows ho… | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Todos are still in the list after the page is reloaded | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| Submitting an empty todo shows a message and leaves the list unchanged | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| The todo list can be downloaded as a PDF file (control) | broken | broken, broken, could_not_test | yes | [0.0, 0.0] |
=======
| Anyone can enter as a guest and use the tools without signing up or gi… | works | works | yes | [10.0] |
| Once inside as a guest, the page shows both a currency converter and a… | works | works | yes | [10.0] |
| The converter changes an amount between US dollars, euros, British pou… | works | works | yes | [10.0] |
| Typing an empty, non-numeric or negative amount into the converter sho… | works | works | yes | [10.0] |
| A todo can be added, marked as done and deleted, and the list shows ho… | works | works | yes | [10.0] |
| Todos are still in the list after the page is reloaded | works | works | yes | [10.0] |
| Submitting an empty todo shows a message and leaves the list unchanged | works | works | yes | [10.0] |
| The todo list can be downloaded as a PDF file (control) | broken | broken | yes | [0.0] |
>>>>>>> ai/tour-guide
