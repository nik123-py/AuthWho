# AuthWho evaluation report

Status: 2026-10-14. Covers every core metric of proposal Section 13. Every number below was produced by a script in `experiments/` whose command, seed and dataset sizes are recorded in `experiments/results/`. Confidence intervals are 95% percentile bootstrap intervals over users (2000 resamples, seed 0) unless stated otherwise.

## Read this first: where the numbers come from

| Source | What it is | What it can and cannot show |
|---|---|---|
| Public datasets (real people) | CMU keystroke benchmark (51 users), Aalto 136M keystrokes (500-user subset), Balabit (10 users), SapiMouse (120 users) | Real behaviour, one channel at a time. Baselines and design choices |
| Chimeric users | Each SapiMouse user paired with a seeded Aalto typist | Fusion on real behaviour, assuming a person's typing and mouse use are independent |
| Synthetic cohort | 25 generated people, 6 sessions each over at least 3 days (`ml/synthetic.py`), with parameters fitted to the public data | Exercises the whole system end to end, including drift, friction and takeovers. **Not measurements of real people** |
| Consented volunteer dataset | 20 to 25 classmates, as planned in Section 13 | **Not collected yet.** The proposal's headline numbers come from it |

The proposal's P3 criterion ("fused score beats each single channel on volunteer data") and the headline targets (fused EER below 5% within about a minute; at most one step-up per two hours) can only be confirmed on the volunteer dataset. The results here say how the system behaves on real single-channel data and on synthetic multi-channel data.

## 1. Keystroke channel (FAR, FRR, EER, ROC-AUC)

CMU benchmark, Killourhy and Maxion standard protocol (train 200 repetitions, test the other 200 and 5 repetitions from each other user), 51 users, 20,400 repetitions. `experiments/results/cmu_standard_protocol.md`.

| Detector | Mean EER [95% CI] | Mean ROC-AUC [95% CI] |
|---|---|---|
| Scaled Manhattan | 0.096 [0.076, 0.116] | 0.954 [0.940, 0.967] |
| One-Class SVM | 0.107 [0.086, 0.127] | 0.943 [0.928, 0.959] |
| Gaussian Mixture Model | 0.103 [0.086, 0.121] | 0.953 [0.941, 0.964] |
| Isolation Forest | 0.089 [0.069, 0.109] | 0.963 [0.948, 0.976] |
| Published scaled Manhattan (Killourhy and Maxion 2009) | 0.096 | not reported |

Target "match or beat the best EER of about 9.6%": met. Scaled Manhattan reproduces 0.096; Isolation Forest reaches 0.089. FAR and FRR are equal at the EER by definition; `ml/metrics.py` also computes them at any threshold.

## 2. Privacy cost of key categories

The live system sees only seven key categories. Same detectors and protocol, category-level (`kf-1`) against key-identity features. Cost is the paired per-user EER difference, category minus key-pair. `experiments/results/category_vs_keypair.md`.

| Dataset | Detector | Key-pair EER | Category EER | Cost [95% CI] |
|---|---|---|---|---|
| CMU (one fixed password) | Scaled Manhattan | 0.096 | 0.161 | +0.065 [0.049, 0.082] |
| CMU | Isolation Forest | 0.089 | 0.157 | +0.069 [0.054, 0.085] |
| Aalto (500 users, 7,078 windows of 50 presses) | Scaled Manhattan | 0.128 | 0.111 | -0.017 [-0.021, -0.012] |
| Aalto | One-Class SVM | 0.149 | 0.145 | -0.004 [-0.010, 0.003] |

On a single repeated password, key identity matters (5 to 7 points of EER). On transcription typing, closer to the free text AuthWho sees, categories are as good or better. The privacy choice therefore costs little or nothing in the live setting.

## 3. Pointer channel, mouse and touchpad

Live `pf-1` features over 30-stroke windows. `experiments/results/pointer_baselines.md`.

| Setting | Users | Best detector | Mean EER [95% CI] | Mean ROC-AUC |
|---|---|---|---|---|
| Balabit (labelled test sessions) | 10 | One-Class SVM | 0.163 [0.100, 0.217] | 0.889 |
| SapiMouse, 30 strokes | 119 | Scaled Manhattan | 0.158 [0.124, 0.196] | 0.857 |
| SapiMouse, 10 strokes | 120 | One-Class SVM | 0.219 [0.193, 0.244] | 0.845 |
| Synthetic cohort, mouse users | 15 | Scaled Manhattan (live model) | 0.081 [0.046, 0.118] | 0.969 |
| Synthetic cohort, touchpad users | 10 | Scaled Manhattan (live model) | 0.155 [0.127, 0.181] | 0.915 |

Mouse versus touchpad on real people: **not measured**. Neither public dataset labels the device per session. In the synthetic cohort, touchpad users are harder to verify than mouse users, as expected from slower, clutched strokes.

## 4. Fusion and continuous trust

| Data | Users | Keystroke EER | Pointer EER | Fused EER [95% CI] | Fused ROC-AUC |
|---|---|---|---|---|---|
| Chimeric (real data, paired) | 119 | 0.144 [0.123, 0.165] | 0.197 [0.163, 0.235] | 0.089 [0.072, 0.109] | 0.956 |
| Synthetic cohort | 25 | 0.118 [0.096, 0.142] | 0.092 [0.054, 0.135] | 0.063 [0.047, 0.079] | 0.980 [0.973, 0.987] |

An attempt is one 50-press keystroke window plus the nearest 30-stroke pointer window, about a minute of active use. On the synthetic cohort the fused EER is lower than keystroke alone (paired difference -0.055 [-0.074, -0.037]) and lower than pointer alone on average (-0.029 [-0.069, 0.006]; the interval includes zero). The page-interaction channel separates people poorly (synthetic EER 0.433 [0.408, 0.458]), partly because the generator gives everyone similar interaction habits; it is shown on the dashboard but carries no weight in trust until it is validated (ruling R15).

## 5. Time to detect an impostor

Synthetic cohort: another user's full test session replayed against a victim's profile, starting from full trust (10 attackers per victim, 250 takeovers). `experiments/results/synthetic_evaluation.json`.

| Threshold | Detected | Active seconds to detect, median (90th percentile) | Actions to detect, median |
|---|---|---|---|
| Trust below 75 (step-up before high-risk actions) | 249 of 250 (99.6%) | 24 (86) | 200 |
| Trust below 50 (strong deviation) | 247 of 250 (98.8%) | 53 (193) | 380 |

Live system, real browser: in the end-to-end tests, a typist with a different rhythm brings trust below 75 within the first windows after taking over, and adding a payee then asks for a step-up. The live takeover demo reliability is in section 11.

## 6. Bot and replay detection

| Attack | Detected | Notes |
|---|---|---|
| Scripted typing with machine-regular timing | 50 of 50 (100%) | Flagged as confirmed automation; the session ends |
| Straight, constant-speed pointer movement | 50 of 50 (100%) | Flagged as confirmed automation |
| Exact replay of a stored window | 125 of 125 (100%) | Strong deviation; step-up |
| Replay with 1% jitter added | 0 of 125 (0%) | **Not detected.** The replay check is exact by design |
| False alarms on genuine behaviour | 0 of 7,078 Aalto, 0 of 776 SapiMouse and 0 of 4,258 synthetic windows flagged as automation | The pointer speed check flags 1.3% of genuine Balabit windows (coarse remote-desktop timestamps), so speed alone never ends a session |

Network replay (re-sending a captured batch) is rejected by the collector's sequence and nonce checks and was confirmed in the end-to-end tests.

## 7. Scoring latency

In-process time per window for feature extraction, scoring and the trust update, on one test session (65 windows): p50 0.9 ms, p95 4.9 ms. Batch transport, the Redis stream and database writes are not included; end-to-end latency from a batch arriving to a trust update is dominated by the worker's polling interval and the time needed to complete a window.

## 8. Robustness under drift

Synthetic cohort, keystroke channel: EER for test sessions recorded on an enrollment day 0.064 [0.026, 0.099] (4 users had such a session) against 0.104 [0.082, 0.127] on later days (25 users). Behaviour drifts across days, and EER rises by about four points. Updating profiles from verified sessions (ruling R8) is the planned remedy. Real drift (new keyboard, tiredness, time of day) needs the volunteer dataset.

## 9. Robustness under attack

Population-statistics attack (Serwadda and Phoha): keystroke windows from a typist whose parameters are the population medians, scored against each synthetic user. Keystroke EER against this attack is 0.136 [0.095, 0.183] against 0.116 [0.095, 0.139] for ordinary zero-effort impostors. A population-average typist is somewhat harder to reject than a random other person. The population-likeness check from the proposal is not implemented yet. The volunteer mimicry study is a stretch goal and was not run.

## 10. User friction

Synthetic cohort, genuine test sessions (100 sessions, 17.4 active hours): strong-deviation episodes, each of which asks for a step-up before continuing, occurred **1 time in 17.4 hours (0.06 per hour; per-user mean 0.08 [0.00, 0.24])**, below the target of one per two hours. Moderate-deviation episodes, which ask for a step-up only before a high-risk action, occurred 32.9 times per hour. A genuine user adding a payee may therefore sometimes be asked to confirm.

These constants (ruling R15) were chosen on this same cohort, so the friction figure is optimistic until it is re-measured on volunteers. The earlier constants (ruling R13), chosen on chimeric data without a friction measure, gave 8 step-ups per hour here.

## 11. Live system checks

| Check | Result |
|---|---|
| Unit and integration tests | Python suite and Vitest suites passing (see the README for commands) |
| End-to-end tests in Chromium against the whole stack | 6 scenarios: no characters captured, replay rejected, takeover with passed step-up, takeover with failed step-up ending the session, insufficient signal for scrolling only, dashboard showing every decision with its explanation |
| Live takeover demo reliability | **10 of 10 runs passed** (95 to 107 seconds each, full stack started fresh every run); `experiments/results/demo_reliability.md` |

## 12. Not measured, and why

| Metric | Reason |
|---|---|
| Headline EER and friction on real multi-channel behaviour | Volunteer dataset not collected (needs consent forms and any institutional approval) |
| Mouse versus touchpad on real people | No public dataset labels the device |
| Real drift across days | Needs the volunteer dataset |
| Mimicry attack | Stretch goal |
| End-to-end scoring latency in the deployed system | In-process latency only so far |
