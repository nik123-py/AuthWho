# Fusion and trust on chimeric users (P3, indicative)

Command: `python -m experiments.fusion_chimeric`. Seed 0. Python 3.14.6, numpy 2.5.3, scikit-learn 1.9.1.

**This is not the P3 success criterion.** The proposal asks for fusion to beat each single channel on the consented volunteer dataset, which is not collected yet. No public dataset has keyboard and mouse data from the same people, so each SapiMouse user is paired with a seeded random Aalto participant (a chimeric user), which assumes the two channels are independent. All scoring uses the live runtime code (`kf-1`, `pf-1`, `ml/profile.py`, `ml/trust.py`). See the docstring of `experiments/fusion_chimeric.py` for the protocol.

## Score fusion (119 chimeric users)

An attempt is one 50-press keystroke window plus one 30-stroke pointer window. Mean per-user values with 95% bootstrap intervals over users.

| Score | Mean EER [95% CI] | Mean ROC-AUC [95% CI] |
|---|---|---|
| keystroke | 0.1439 [0.1230, 0.1648] | 0.9086 [0.8892, 0.9269] |
| pointer | 0.1970 [0.1633, 0.2349] | 0.8381 [0.8003, 0.8702] |
| fused | 0.0893 [0.0717, 0.1087] | 0.9564 [0.9441, 0.9680] |

- Fused minus keystroke EER: -0.0546 [-0.0740, -0.0361]
- Fused minus pointer EER: -0.1077 [-0.1400, -0.0775]
- Fused minus the better single channel per user (an oracle choice): +0.0111 [0.0006, 0.0226]

## Trust simulation

Genuine streams: 119 users, 1138 windows in total (the user's own test windows, alternating channels); median of each user's minimum trust 93.5. Impostor streams: 2380 (another chimeric user's first 6 keystroke and 6 pointer windows against this user's templates). Trust below 75 means moderate deviation (step-up before high-risk actions); below 50 means strong deviation (step-up before continuing).

| Threshold | Genuine users ever below | Impostor streams detected within 12 windows | Windows to detect, median | 90th percentile |
|---|---|---|---|---|
| 75 | 7 (0.059) | 0.668 | 4.0 | 6.0 |
| 50 | 2 (0.017) | 0.455 | 6.0 | 9.0 |

Chosen settings: TAU 0.1, PENALTY 10.0, REWARD 5.0 (ruling R15, chosen on the synthetic cohort against the friction target; see synthetic_evaluation.md). The sweep below shows how other settings behave on this chimeric data.

| TAU | PENALTY | REWARD | Genuine below 75 | Impostors below 75 | Genuine below 50 | Impostors below 50 |
|---|---|---|---|---|---|---|
| 0.1 | 10 | 5 | 7 | 0.668 | 2 | 0.455 |
| 0.15 | 10 | 5 | 8 | 0.704 | 2 | 0.515 |
| 0.2 | 10 | 5 | 9 | 0.732 | 2 | 0.553 |
| 0.25 | 10 | 5 | 11 | 0.800 | 2 | 0.584 |
| 0.25 | 12 | 5 | 23 | 0.846 | 7 | 0.646 |
| 0.3 | 12 | 5 | 27 | 0.893 | 7 | 0.696 |

## Limits

- Chimeric pairing assumes independence between a person's typing and mouse behaviour.
- Genuine test data per user is small (about 6 keystroke and 2 pointer windows), so the genuine false step-up rate is measured over short streams and is not a per-hour friction figure.
- Genuine pointer tests come from SapiMouse's 1-minute session, recorded right after enrollment, so drift across days is not covered.
