# CMU keystroke benchmark, standard protocol

Command: `python -m experiments.cmu_standard_protocol`. Dataset `data/cmu/DSL-StrongPasswordData.csv` (SHA-256 `b11d23538b1865fa6ecf4e8b78567caa312e9c1027604bb022fcc6ad7eaa7a33`), 51 subjects, 20400 rows, 31 features. Seed 0.

Protocol (Killourhy and Maxion 2009): per subject, train on the first 200 repetitions, test on the remaining 200 and on the first 5 repetitions of each of the other 50 subjects. EER and ROC-AUC are computed per subject and averaged; the 95% interval is a percentile bootstrap over subjects (2000 resamples).

| Detector | Mean EER | SD | 95% CI of mean EER | Mean ROC-AUC | 95% CI of mean AUC |
|---|---|---|---|---|---|
| scaled_manhattan | 0.0962 | 0.0694 | [0.0763, 0.1156] | 0.9538 | [0.9397, 0.9674] |
| ocsvm | 0.1069 | 0.0724 | [0.0861, 0.1272] | 0.9433 | [0.9279, 0.9587] |
| gmm | 0.1033 | 0.0614 | [0.0860, 0.1209] | 0.9527 | [0.9409, 0.9643] |
| isolation_forest | 0.0888 | 0.0714 | [0.0690, 0.1091] | 0.9625 | [0.9477, 0.9758] |
| Published: Killourhy and Maxion 2009, scaled Manhattan | 0.096 | 0.069 | not reported | not reported | |

Note: EER here is interpolated linearly at the FAR and FRR crossing (see `ml/metrics.py`). Detector settings are the defaults in `ml/models/`, which are not identical to the paper's (for example the One-Class SVM here z-scores features and uses nu = 0.05).
