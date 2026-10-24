# Evaluation: fake_claim

Run on 2026-10-24 17:05 UTC. 1 runs.

**Result: FAIL**

## Checks

- PASS: every run finished
- PASS: no wrong verdicts
- PASS: every claim steady (same verdict in 1 of 1 runs)
- FAIL: majority verdict is the expected one for every claim
- PASS: TalNex score spread within 10 points
- PASS: no unexpected red flags

## Numbers

- Verdicts matching the expected answer: 4 of 6 (66.7%)
- Wrong verdicts: 0
- Could not test / no result (never a wrong answer): 2
- TalNex score per run (out of 100): [47.0] (spread 0.0)
- Red flags per run: [0]
- Seconds per run: [330]
- Cost per run (US dollars): [0.0243]

## Claims

| Claim | Expected | Verdicts per run | Steady | Feature scores |
|---|---|---|---|---|
| The About page explains what CaptionIt is | works | works | yes | [10.0] |
| The landing page has a link that opens the try page | works | works | yes | [10.0] |
| The try page has a photo picker and a Write my caption button | works | works | yes | [6.3] |
| Upload a photo and CaptionIt writes a caption describing it | broken | broken | yes | [0.0] |
| Choose a photo and press Write my caption, and the caption appears und… | broken | could_not_test | yes | [] |
| Captions can be translated into other languages (control) | broken | could_not_test | yes | [] |
