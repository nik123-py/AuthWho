# Synthetic cohort calibration

Synthetic cohort: 25 users, seed 2026, 150 sessions; 3157 keystroke and 1101 pointer windows (non-overlapping). Real references: Aalto subset (7078 keystroke windows) and SapiMouse 3-minute sessions (611 pointer windows). Values are p10 / median / p90 of the live window features.

Bot checks flagged 0 of 4258 synthetic windows.

| Feature | Synthetic | Real |
|---|---|---|
| dwell_mean | 87.5 / 128 / 182 | 87.1 / 116 / 161 |
| flight_median | -17.3 / 57.5 / 143 | 4 / 65 / 161 |
| dd_median | 119 / 167 / 260 | 116 / 171 / 282 |
| rollover_rate | 0.0612 / 0.224 / 0.592 | 0.0408 / 0.184 / 0.449 |
| correction_rate | 0 / 0.04 / 0.1 | 0 / 0.04 / 0.14 |
| typing_rate | 3.26 / 5.19 / 7.28 | 2.5 / 4.46 / 6.99 |
| pause_rate | 0 / 0.0204 / 0.0816 | 0 / 0.0204 / 0.0408 |
| velocity_mean | 0.535 / 0.807 / 1.38 | 0.797 / 1.16 / 1.64 |
| efficiency_mean | 0.726 / 0.819 / 0.88 | 0.659 / 0.758 / 0.849 |
| curvature_mean | 0.061 / 0.115 / 0.281 | 0.0713 / 0.113 / 0.187 |
| duration_mean | 278 / 392 / 524 | 529 / 695 / 897 |
| click_rate | 0.3 / 0.4 / 0.867 | 0.767 / 0.967 / 1 |
| pre_click_pause_mean | 24 / 48.8 / 104 | 34.3 / 63.1 / 118 |

Known differences: synthetic pointer strokes are shorter and end in a click less often than SapiMouse strokes, because SapiMouse is a click-the-target task while the synthetic sessions model web browsing and form filling. Synthetic results must be read as a test of the pipeline and method, not as measurements of real people.
