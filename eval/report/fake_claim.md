# Evaluation: fake_claim

<<<<<<< HEAD
Run on 2026-10-24 16:09 UTC. 3 runs.
=======
Run on 2026-10-24 17:31 UTC. 1 runs. email sign-up on (new EMAIL_LOGIN_SECRET)
>>>>>>> ai/tour-guide

**Result: FAIL**

## Checks

- PASS: every run finished
<<<<<<< HEAD
- FAIL: no wrong verdicts
- PASS: every claim steady (same verdict in 2 of 3 runs)
- PASS: majority verdict is the expected one for every claim
- FAIL: TalNex score spread within 10 points
=======
- PASS: no wrong verdicts
- PASS: every claim steady (same verdict in 1 of 1 runs)
- FAIL: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
>>>>>>> ai/tour-guide
- PASS: no unexpected red flags

## Numbers

<<<<<<< HEAD
- Verdicts matching the expected answer: 16 of 18 (88.9%)
- Wrong verdicts: 1
- Could not test / no result (never a wrong answer): 1
- TalNex score per run (out of 100): [38.0, 20.0, 26.0] (spread 18.0)
- Red flags per run: [0, 0, 0]
- Seconds per run: [375, 408, 564]
- Cost per run (US dollars): [0.0347, 0.0328, 0.0334]
=======
- Verdicts matching the expected answer: 5 of 6 (83.3%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 1
- TalNex score per run (out of 100): [35.0] (spread 0.0)
- Red flags per run: [0]
- Seconds per run: [333]
- Cost per run (US dollars): [0.0268]
>>>>>>> ai/tour-guide

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
<<<<<<< HEAD
| The About page explains what CaptionIt is | works | works, broken, works | yes | [10.0, 0.0, 6.5] |
| The landing page has a link that opens the try page | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| The try page has a photo picker and a Write my caption button | works | works, works, works | yes | [5.1, 5.8, 6.3] |
| Upload a photo and CaptionIt writes a caption describing it | broken | broken, broken, broken | yes | [0.0, 0.0, 0.0] |
| Choose a photo and press Write my caption, and the caption appears und… | broken | could_not_test, broken, broken | yes | [0.0, 0.0] |
| Captions can be translated into other languages (control) | broken | broken, broken, broken | yes | [0.0, 0.0, 0.0] |
=======
| The About page explains what CaptionIt is | works | works | yes | [7.4] |
| The landing page has a link that opens the try page | works | works | yes | [10.0] |
| The try page has a photo picker and a Write my caption button | works | works | yes | [5.1] |
| Upload a photo and CaptionIt writes a caption describing it | broken | broken | yes | [0.0] |
| Choose a photo and press Write my caption, and the caption appears und… | broken | could_not_test | yes | [] |
| Captions can be translated into other languages (control) | broken | broken | yes | [0.0] |
>>>>>>> ai/tour-guide
