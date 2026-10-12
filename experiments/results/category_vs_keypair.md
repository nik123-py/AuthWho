# Privacy cost of key categories (P1-3)

Command: `python -m experiments.category_vs_keypair`. Seed 0. Python 3.14.6, numpy 2.5.3, scikit-learn 1.9.1.

The live system sees only key categories (`kf-1`). This experiment measures the cost of that choice by comparing it with features that know which key was pressed, using the same detectors and protocol. The cost column is the mean per-user EER difference, category minus key-pair, with a paired percentile bootstrap interval over users (2000 resamples). A positive cost means categories are less accurate.

## Datasets

- CMU: `data/cmu/DSL-StrongPasswordData.csv` (SHA-256 `b11d23538b1865fa6ecf4e8b78567caa312e9c1027604bb022fcc6ad7eaa7a33`), 51 users, 20400 repetitions. Key-pair variant: the 31 published per-key features. Category variant: `kf-1` (35 features) from the rebuilt presses. Standard protocol (train 200, genuine 200, impostor 5 repetitions from each other user).
- Aalto 136M keystrokes: seeded subset of 500 participants from https://userinterfaces.aalto.fi/136Mkeystrokes/data/Keystrokes.zip (manifest SHA-256 `e5ff68eb32a83244823a5b63f29d410b12ccd07166f71db4b4b6a57f3f447059`). Non-overlapping windows of 50 presses; 500 users with at least 8 windows kept, 7078 windows in total (0 skipped as invalid). First half of each user's windows trains, second half is genuine, the first window of every other user is impostor. Key-pair variant: 50 features (`ml/keypair.py`); category variant: `kf-1` (35 features).

## CMU

| Detector | Key-pair EER [95% CI] | Category EER [95% CI] | Cost (category minus key-pair) [95% CI] | Key-pair AUC | Category AUC |
|---|---|---|---|---|---|
| scaled_manhattan | 0.0962 [0.0763, 0.1156] | 0.1611 [0.1331, 0.1897] | +0.0649 [0.0490, 0.0820] | 0.9538 | 0.8967 |
| ocsvm | 0.1069 [0.0861, 0.1272] | 0.1708 [0.1431, 0.1988] | +0.0640 [0.0477, 0.0811] | 0.9433 | 0.8916 |
| gmm | 0.1033 [0.0860, 0.1209] | 0.1563 [0.1307, 0.1820] | +0.0530 [0.0379, 0.0696] | 0.9527 | 0.9099 |
| isolation_forest | 0.0888 [0.0690, 0.1091] | 0.1574 [0.1315, 0.1849] | +0.0686 [0.0538, 0.0852] | 0.9625 | 0.9107 |

## Aalto

| Detector | Key-pair EER [95% CI] | Category EER [95% CI] | Cost (category minus key-pair) [95% CI] | Key-pair AUC | Category AUC |
|---|---|---|---|---|---|
| scaled_manhattan | 0.1277 [0.1190, 0.1378] | 0.1112 [0.1031, 0.1208] | -0.0165 [-0.0211, -0.0118] | 0.9340 | 0.9438 |
| ocsvm | 0.1486 [0.1392, 0.1596] | 0.1450 [0.1355, 0.1553] | -0.0037 [-0.0099, 0.0028] | 0.9091 | 0.9095 |
| gmm | 0.1548 [0.1455, 0.1652] | 0.1523 [0.1434, 0.1624] | -0.0025 [-0.0096, 0.0047] | 0.9092 | 0.9095 |
| isolation_forest | 0.1942 [0.1856, 0.2026] | 0.1719 [0.1630, 0.1805] | -0.0223 [-0.0309, -0.0129] | 0.8773 | 0.8953 |

## Limits

- CMU is one fixed password, so its key-pair variant is the strongest possible case for key identity.
- Aalto participants transcribe given sentences; this is closer to free text than CMU but is not the composed free text the live system sees.
- Aalto users here have few training windows (half of at least eight), so absolute EERs are higher than with a longer enrollment. The comparison between variants is paired and uses identical windows.
