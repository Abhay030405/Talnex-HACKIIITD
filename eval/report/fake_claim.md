# Evaluation: fake_claim

Run on 2026-10-24 15:00 UTC. 3 runs. round 3: promises vs steps, fresh visitor, time per step, trimmed text

**Result: FAIL**

## Checks

- PASS: every run finished
- PASS: no wrong verdicts
- PASS: every claim steady (same verdict in 2 of 3 runs)
- FAIL: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 13 of 18 (72.2%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 5
- TalNex score per run (out of 100): [38.0, 37.0, 35.0] (spread 3.0)
- Red flags per run: [0, 0, 0]
- Seconds per run: [429, 315, 261]
- Cost per run (US dollars): [0.0817, 0.0791, 0.0808]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| The About page explains what CaptionIt is | works | works, works, works | yes | [10.0, 4.0, 4.0] |
| The landing page has a link that opens the try page | works | works, works, works | yes | [10.0, 10.0, 10.0] |
| The try page has a photo picker and a Write my caption button | works | works, works, works | yes | [5.1, 5.8, 5.1] |
| Upload a photo and CaptionIt writes a caption describing it | broken | broken, broken, could_not_test | yes | [0.0, 0.0] |
| Choose a photo and press Write my caption, and the caption appears und… | broken | could_not_test, could_not_test, broken | yes | [0.0] |
| Captions can be translated into other languages (control) | broken | broken, could_not_test, could_not_test | yes | [0.0] |
