# Pointer baselines on public mouse datasets (P2-2)

Command: `python -m experiments.pointer_baselines`. Seed 0. Python 3.14.6, numpy 2.5.3, scikit-learn 1.9.1. Features: live `pf-1` (22 features) over windows of strokes.

- Balabit: `https://codeload.github.com/balabit/Mouse-Dynamics-Challenge/zip/refs/heads/master` (SHA-256 `7858b7abffc5a8b34524dc96b47371ed2c9179f50a06487ff02b243fe8ccbc27`). Train on 30-stroke windows (stride 15, at most 400 per user) from training sessions; each labelled test session is scored by the mean of its 30-stroke windows; labels from `public_labels.csv`.
- SapiMouse: `http://www.ms.sapientia.ro/~manyi/sapimouse/sapimouse.zip` (SHA-256 `c843ae25d82eb827fa92f26489a3d4ae27492ef98fa179646783af4525f9fa60`). Train on the 3-minute session; genuine tests are the windows of the user's 1-minute session; impostor tests are the first window of every other user's 1-minute session.

Mean per-user EER and ROC-AUC with 95% percentile bootstrap intervals over users (2000 resamples).

| Setting | Users | Detector | Mean EER [95% CI] | Mean ROC-AUC [95% CI] |
|---|---|---|---|---|
| balabit_30 | 10 | scaled_manhattan | 0.2079 [0.1394, 0.2706] | 0.8473 [0.7962, 0.9034] |
| balabit_30 | 10 | ocsvm | 0.1626 [0.1005, 0.2171] | 0.8894 [0.8445, 0.9377] |
| balabit_30 | 10 | gmm | 0.2023 [0.1275, 0.2689] | 0.8485 [0.7793, 0.9177] |
| balabit_30 | 10 | isolation_forest | 0.1817 [0.1117, 0.2435] | 0.8742 [0.8182, 0.9322] |
| sapimouse_30 | 119 | scaled_manhattan | 0.1577 [0.1236, 0.1956] | 0.8574 [0.8220, 0.8901] |
| sapimouse_30 | 119 | ocsvm | 0.1651 [0.1298, 0.2046] | 0.8462 [0.8071, 0.8816] |
| sapimouse_30 | 119 | gmm | 0.1713 [0.1339, 0.2117] | 0.8452 [0.8066, 0.8802] |
| sapimouse_30 | 119 | isolation_forest | 0.2118 [0.1685, 0.2558] | 0.8059 [0.7629, 0.8483] |
| sapimouse_10 | 120 | scaled_manhattan | 0.2455 [0.2211, 0.2718] | 0.8260 [0.7985, 0.8513] |
| sapimouse_10 | 120 | ocsvm | 0.2189 [0.1930, 0.2442] | 0.8452 [0.8198, 0.8706] |
| sapimouse_10 | 120 | gmm | 0.2201 [0.1986, 0.2426] | 0.8494 [0.8277, 0.8709] |
| sapimouse_10 | 120 | isolation_forest | 0.2634 [0.2385, 0.2907] | 0.7998 [0.7725, 0.8257] |

## Mouse and touchpad

Both datasets are treated as mouse data. SapiMouse's authors note that some participants used a touchpad, but sessions are not labelled by device, so a separate touchpad result is **not measured** here. It needs the consented volunteer dataset, where the pointing device is recorded per session.

## Limits

- Balabit has only 10 users, so its interval is wide.
- In SapiMouse each user's genuine test comes from a single one-minute session, so per-user EERs are coarse (few genuine windows), especially at 30 strokes.
- Published SapiMouse results use deep features on short raw segments and are not directly comparable with these hand-crafted window features.
