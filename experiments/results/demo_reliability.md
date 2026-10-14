# Live takeover demo reliability (P5)

Command: `python -m experiments.demo_reliability --runs 10`. Each run starts the whole stack and runs `tests/e2e/test_authwho_e2e.py::test_takeover_step_up_passed_by_the_genuine_user` in Chromium.

**10 of 10 runs passed.**

| Run | Result | Seconds |
|---|---|---|
| 1 | passed | 95.1 |
| 2 | passed | 95.1 |
| 3 | passed | 94.8 |
| 4 | passed | 96.4 |
| 5 | passed | 97.3 |
| 6 | passed | 98.2 |
| 7 | passed | 98.9 |
| 8 | passed | 97.0 |
| 9 | passed | 106.5 |
| 10 | passed | 95.4 |
