# AuthWho project history

A hand-off note for the next session. Durable details live in `PLAN.md` (phases and rulings R1 to R11), `PROGRESS.md` (task status), `docs/interfaces.md` (shared contracts, change log) and `docs/dependencies.md` (approved packages). The `.tex` proposal governs; `AuthWho_Project_Proposal-1.pdf` and `AuthWho_Master_Prompt.md` are older and are superseded where they disagree (ruling R3).

## How work is done

- Phases P0 to P6 from `PLAN.md`, in order. Each phase ends with the full test suite, a privacy review, a commit named after the phase, a phase report and a stop for the owner's OK.
- From 2026-10-12 the owner asked for **no subagents**: the orchestrator does each task itself, one by one, following the agent briefs in `.claude/agents/` as conventions (test-driven development, no em dashes, no invented metrics).
- Tests: `.venv/Scripts/python -m pytest` from the repo root (Docker Desktop must be running for integration tests); `npm test` in the workspaces for TypeScript.

## Timeline

### 2026-10-09: setup
- Skills copied unchanged into `.claude/skills/`; seven agent briefs in `.claude/agents/`.
- `PLAN.md`, `docs/interfaces.md` and `docs/dependencies.md` written and approved by the owner.

### P0 (committed as `5e9621e`): SDK, event schema, consent form, demo web app
- Browser SDK (`sdk/`): captures key categories only, never characters; password fields excluded; batching, HMAC signing, sequence numbers, retries. 121 Vitest tests.
- Collector (`server/collector/`): session and stream handshake, signature, sequence and nonce checks, schema validation, rate limit, `aw:events` Redis stream with 24 h trim; dump tool.
- PostgreSQL migrations `0001` to `0003` (users, sessions, research consent time); retention job; encrypted volunteer research export (`server/research/`).
- Demo app backend (`demo_app/backend/`) and frontend (`demo_app/frontend/`): login, consent with opt-outs and device choice, "What we collect" page.
- GitHub Actions workflow (runs once a remote exists). Privacy review: first FAIL (withdrawal), re-review PASS.

### 2026-10-12: P1 in progress (not yet committed)

**P1-2, CMU part: done.**
- `ml/metrics.py` (FAR, FRR, interpolated EER, ROC-AUC, bootstrap CI) and `ml/models/` (scaled Manhattan, One-Class SVM, GMM, Isolation Forest, all JSON-serialisable) were written in an earlier session.
- New: `ml/datasets/cmu.py` (loader and the Killourhy and Maxion standard protocol), `ml/evaluation.py` (per-user EER and AUC, summary with bootstrap CI), `experiments/cmu_standard_protocol.py`.
- Result (`experiments/results/cmu_standard_protocol.md`, seed 0, 51 subjects):

| Detector | Mean EER (sd) | Mean ROC-AUC |
|---|---|---|
| Scaled Manhattan | 0.0962 (0.0694) | 0.9538 |
| One-Class SVM | 0.1069 (0.0724) | 0.9433 |
| GMM | 0.1033 (0.0614) | 0.9527 |
| Isolation Forest | 0.0888 (0.0714) | 0.9625 |
| Published scaled Manhattan (Killourhy and Maxion 2009) | 0.096 (0.069) | not reported |

**P1-1: done.**
- `server/features/`: input types, `kf-1` schema (35 features with documented fill rules and a quality score), pure extractor `extract_keystroke`, and `KeystrokeWindower` (pairs key-down and key-up by `press_id`, 50-press windows, stride 25, drops orphaned key-downs).
- `server/worker/`: `python -m server.worker [--env-file .env] [--once]`. Consumer group `features` on `aw:events`; per-stream windowing; skips unknown sessions, exempt users and opted-out channels; stores windows AES-256-GCM encrypted with the window id as associated data.
- Migration `0004_windows.sql` (adds `stream_id` beyond the original contract); retention rule `delete_expired_windows` (30 days); withdrawal now deletes `windows` and deletes the `users` row first, while the worker locks that row before inserting, so no window can slip in during a withdrawal.
- `docs/interfaces.md` change log entry 1.2.
- Verified: full Python suite **393 passed** (integration tests included); dev database migrated; worker and retention run cleanly against Docker Compose.

**P1-3: done (later on 2026-10-12).**
- `ml/datasets/aalto.py`: `RangeFile` reads the official zip over HTTP range requests; `fetch_subset` extracted a seeded subset of 500 participants (55 MB, about 4 minutes) into `data/aalto/` with a `subset.json` manifest; `parse_keystroke_file` keeps only category, key code and times and discards text at parse time. `ml/datasets/presses.py` holds the shared offline `Press` type; `ml/datasets/cmu.py` gained `presses_from_row` (checked on all 20,400 CMU rows).
- `ml/keypair.py`: the category variant is exactly `kf-1`; the key-pair variant shares the 20 identity-free `kf-1` features and adds dwell for 10 frequent keys and down-down latency for the 20 most common English bigrams (fixed a priori).
- `experiments/category_vs_keypair.py` and `experiments/results/category_vs_keypair.md`: on CMU, categories cost +0.053 to +0.069 EER (CI excludes zero); on Aalto (transcription, 50-press windows, 500 users, 7,078 windows) categories are as good or better (cost -0.022 to -0.003).
- Ruling R12 (Aalto subset). P1 privacy review done by the orchestrator: PASS.
- Verified: 426 Python tests and 217 Vitest tests passing.

Earlier notes on the Aalto archive, kept for reference:
- Aalto 136M keystrokes: official archive `https://userinterfaces.aalto.fi/136Mkeystrokes/data/Keystrokes.zip` is 1.57 GB, 168,597 entries (`Keystrokes/files/<id>_keystrokes.txt`, plus `metadata_participants.txt` and `readme.txt`). Licence: free for research and non-commercial use with attribution.
- File format (from the archive's `readme.txt`): tab-separated with a header row, columns `PARTICIPANT_ID, TEST_SECTION_ID, SENTENCE, USER_INPUT, KEYSTROKE_ID, PRESS_TIME, RELEASE_TIME, LETTER, KEYCODE`; times are epoch ms; `LETTER` holds names such as `SHIFT` for special keys; 15 sentences per participant (participant 100001's file is 97 KB). For some users `LETTER` is missing and `KEYCODE` must be used. `SENTENCE`, `USER_INPUT` and `LETTER` contain text, so the loader must keep only categories, key pairs for the offline comparison, and times.
- Reading the central directory over range requests took about 37 s.
- Decision: do not download the whole archive into this OneDrive folder. Read the zip's central directory with HTTP range requests and fetch only a documented, seeded subset of participant files into `data/aalto/` (gitignored). A working probe is in the session scratchpad; the proper fetcher still has to be written in `ml/datasets/aalto.py`.

## Next steps

1. P2 (owner asked on 2026-10-12 to keep going until the system works end to end with ML): pointer and interaction features (`pf-1`, `if-1`) and their windowers, wired into the worker.
2. P2: Balabit and SapiMouse pointer baselines (mouse; touchpad needs volunteer data).
3. P2: JSON profile templates, enrollment at 20 windows, runtime channel scorers. Then P3 fusion and trust, P4 policy and TOTP, P5 dashboard.

## Open items carried forward
- P0-5 follow-up for P5: login token expiry and Secure cookie.
- P4-4: show a notice when `withdrawal_pending` is true.
- Volunteer data collection (owner-run, needs consent forms and any ethics approval) gates the P2 touchpad row, the P3 criterion and the P6 headline numbers.
- Worker window state is in memory: a restart loses partly filled windows (documented in `server/worker/pipeline.py`).
