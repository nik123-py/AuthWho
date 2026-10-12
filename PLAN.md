# AuthWho build plan

Source of truth: `AuthWho_Project_Proposal.tex` (Section 14, "MVP, phased roadmap and stretch goals"). Shared contracts: `docs/interfaces.md`. Approved dependencies: `docs/dependencies.md`. Task status: `PROGRESS.md`.

The orchestrator re-reads this file, `PROGRESS.md` and `docs/interfaces.md` at the start of every phase. Each phase ends with the full test suite run by the orchestrator, a privacy review, a commit named after the phase, a phase report and a stop for the owner's OK.

## MVP scope (proposal Section 14)

Browser SDK and server-side feature extraction; one-class keystroke and pointer models (scaled Manhattan, One-Class SVM, Gaussian Mixture Model); channel fusion into a trust score with an explicit "insufficient signal" state; basic bot and replay checks; a policy engine with TOTP step-up and session termination; a dashboard with explanations and the live demo; and evaluation on the multi-day volunteer dataset.

Out of scope until P0 to P6 meet their criteria and the owner says yes: deep models, ONNX, MLflow, the mimicry study, Keycloak, Prometheus and Grafana, the hash-chained audit log, public deployment.

## Rulings

Conflicts and gaps found while planning, and how they are resolved. New rulings are added here as they arise.

| # | Topic | Ruling | Why |
|---|---|---|---|
| R1 | Key categories | Seven categories: the proposal's six plus `other` | Enter, Escape, punctuation and function keys need a bucket. Approved by the owner on 2026-10-09 |
| R2 | P0 "first sessions recorded" | Met by a manual capture the owner records and inspects. Volunteer collection is run by the owner after consent forms and any institutional ethics approval | Collecting volunteer data depends on people, not code |
| R3 | Proposal PDF | `AuthWho_Project_Proposal-1.pdf` is an older version with phases P0 to P7; the `.tex` governs | The PDF and the `.tex` disagree on scope |
| R4 | Pointing device type | The user declares mouse or touchpad in the consent and enrollment flow | Browsers report both as `pointerType: "mouse"`, so automatic detection is unreliable |
| R5 | Password fields | Keystrokes in password fields are not captured | The category sequence of a password reveals its composition (letters, digits, length) |
| R6 | Strong deviation plus high-risk action | Step-up first; `critical` (block and end the session) only after a failed step-up or on confirmed automation | Proposal Section 7's table says block immediately, but the Section 5 example asks for step-up first. Step-up first protects genuine users from false rejections and matches the friction target |
| R7 | Trust timeline retention | Trust points are kept 30 days, like the windows they derive from | Not listed in the Section 9 table; the shorter period is the safer choice |
| R8 | Profile updates from verified sessions | Deferred until after the MVP | Pipeline step 9 is not in the MVP callout; drift is still measured in P6 |
| R9 | Transport | HTTP POST for batches on `localhost`; WebSocket only for dashboard push; TLS only for the stretch deployment | `localhost` is a secure context for WebCrypto, and the proposal allows HTTPS or WebSocket |
| R11 | Capture dump tool | `python -m server.collector.dump` prints raw batches to the terminal only, for the owner to inspect a capture as P0 requires. It never writes files; redirecting its output to a file is discouraged | The P0 success criterion needs a capture that can be inspected |
| R12 | Aalto dataset size | A seeded subset of 500 participants (seed 0) is read from the official archive with HTTP range requests; the 1.57 GB archive is never downloaded whole | Laptop and OneDrive storage; the subset is documented by a manifest hash in the results |
| R10 | Proposal location | The `.tex` stays at the repository root | The owner placed it there |

## Phases

### P0: SDK, event schema, consent form, demo web app (weeks 1 to 2)

Success criterion (proposal): **Capture verified to contain no characters; first sessions recorded.**
Measured by: the SDK "no characters" unit test passing, the end-to-end browser variant in P4, and a manual capture the owner records and inspects with the dump tool.

| ID | Agent | Task | Depends on |
|---|---|---|---|
| P0-1 | orchestrator | Root `pyproject.toml`, root `package.json` with workspaces, `.venv`, `README.md` | none |
| P0-2 | sdk-engineer | Capture of all event types in `docs/interfaces.md` section 5, key-category mapping, password-field exclusion, opt-outs, batching, HMAC signing, sequence numbers, retry handling; "no characters" test | P0-1 |
| P0-3 | backend-engineer | `docker-compose.yml` (PostgreSQL, Redis without disk persistence), `.env.example`, migration runner, `users` table, collector: session and stream handshake, signature, sequence and nonce checks, schema validation, rate limit, `aw:events` with 24 h trim; dump tool `python -m server.collector.dump <session_id>` | P0-1 |
| P0-4 | backend-engineer | Volunteer research export (encrypted files under `data/volunteer/`) | P0-3 |
| P0-5 | policy-engineer | Demo app backend: users with scrypt passwords, login, consent and opt-out record, pointer-device declaration, session and stream minting through the collector, page registry, stub high-risk actions | P0-1 (builds against the section 4 contract) |
| P0-6 | frontend-engineer | Demo app frontend: login, consent form with opt-outs and device choice, "What we collect" page, free-text, form and browsing pages that load the SDK | P0-1 (builds against the SDK API) |
| P0-7 | qa-engineer | GitHub Actions workflow running pytest and Vitest on every push | P0-1 |
| P0-8 | privacy-reviewer | Review of all P0 changes | P0-2 to P0-7 |

Parallel: P0-2, P0-3, P0-5, P0-6 and P0-7 run together after P0-1. P0-4 follows P0-3.

### P1: Keystroke features and one-class baselines (weeks 3 to 4)

Success criterion (proposal): **EER comparable to published baselines; privacy cost measured.**
Measured by: CMU EER on the Killourhy and Maxion standard protocol reported next to their 9.6% best result, and the EER difference between category-level and key-pair digraphs on CMU and Aalto, all with confidence intervals.

| ID | Agent | Task | Depends on |
|---|---|---|---|
| P1-1 | backend-engineer | `kf-1` keystroke extraction as pure functions, keystroke windowing, worker that reads `aw:events` and writes encrypted windows, 30-day retention job | P0 |
| P1-2 | ml-engineer | Download CMU and Aalto from official sources; loaders; metrics module (FAR, FRR, EER, ROC-AUC, bootstrap confidence intervals); scaled Manhattan, One-Class SVM, GMM and Isolation Forest on the CMU standard protocol | P0 |
| P1-3 | ml-engineer | Category versus key-pair experiment on CMU and Aalto using `server/features` extractors | P1-1, P1-2 |
| P1-4 | privacy-reviewer | Review | P1-1 to P1-3 |

Parallel: P1-1 and P1-2.

### P2: Pointer and interaction features (weeks 5 to 6)

Success criterion (proposal): **Per-user pointer models with EER and AUC, mouse and touchpad separately.**
Measured by: per-user EER and AUC on Balabit and SapiMouse (mouse) and on volunteer data split by device. If no touchpad volunteer data exists yet, the touchpad row is reported as "not measured".

| ID | Agent | Task | Depends on |
|---|---|---|---|
| P2-1 | backend-engineer | Stroke segmentation, `pf-1` pointer and `if-1` interaction extraction and windowing | P1-1 |
| P2-2 | ml-engineer | Balabit and SapiMouse loaders, per-user pointer models and evaluation | P1-2 |
| P2-3 | ml-engineer | JSON profile templates, enrollment training, runtime keystroke and pointer scorers returning channel scores | P1-2, P2-1 |
| P2-4 | backend-engineer | `profiles` table, encrypted template storage, enrollment trigger at 20 windows | P2-3 contract |
| P2-5 | privacy-reviewer | Review | P2-1 to P2-4 |

Parallel: P2-1 and P2-2; then P2-3 and P2-4.

### P3: Channel fusion, continuous trust score, insufficient signal (weeks 7 to 8)

Success criterion (proposal): **Fused score beats each single channel on volunteer data.**
Measured by: EER and ROC-AUC of fused trust against keystroke-only and pointer-only on volunteer sessions, with confidence intervals. Without volunteer data this criterion cannot be measured, and the report will say so.

| ID | Agent | Task | Depends on |
|---|---|---|---|
| P3-1 | ml-engineer | Evidence-weighted fusion, penalty-and-reward trust update, `insufficient_signal` state with freshness rule and its own tests, offline fused versus single-channel evaluation | P2-3 |
| P3-2 | backend-engineer | Worker wiring: windows to scorers to trust engine; `trust_points` table with 30-day retention; publish trust updates on `aw:trust` | P3-1 contract |
| P3-3 | privacy-reviewer | Review | P3-1, P3-2 |

Parallel: P3-1 and P3-2 against the trust update contract.

### P4: Policy engine, TOTP step-up, session termination, bot and replay checks (weeks 9 to 10)

Success criterion (proposal): **End-to-end step-up and termination driven by trust thresholds.**
Measured by: Playwright scenarios in which a simulated takeover lowers trust, triggers TOTP step-up, and a failed step-up ends the session; plus unit tests for every trust level.

| ID | Agent | Task | Depends on |
|---|---|---|---|
| P4-1 | policy-engineer | Policy engine with the section 11 levels and defaults, `policies` table, append-only `decisions` table with trigger and 90-day retention, explanation sentences, session control API, exemptions | P3 |
| P4-2 | policy-engineer | Bot and replay heuristics producing section 10 flags | P3 |
| P4-3 | policy-engineer | Demo backend: TOTP enrollment and step-up with pyotp, high-risk actions through the policy API, status checks on every request, session end | P4-1 |
| P4-4 | frontend-engineer | Demo frontend: TOTP enrollment, step-up prompt, blocked action and session-ended screens | P4-3 contract |
| P4-5 | qa-engineer | Playwright scenarios 1 to 4 from the qa-engineer brief, plus Playwright in CI | P4-1 to P4-4 |
| P4-6 | ml-engineer | Population-statistics synthetic attack generator (for P4-2 tests and P6) | P1-2 |
| P4-7 | privacy-reviewer | Review | all P4 |

Parallel: P4-1, P4-2 and P4-6; then P4-3 and P4-4; then P4-5.

### P5: Dashboard, explanations and live demo mode (weeks 11 to 12)

Success criterion (proposal): **Every decision explained; live takeover demo works reliably.**
Measured by: a test asserting every decision row has a non-empty explanation shown on the dashboard, and the live takeover demo run 10 times with the number of successful runs reported.

| ID | Agent | Task | Depends on |
|---|---|---|---|
| P5-1 | backend-engineer | Admin API and WebSocket (section 13), incident report export; API, worker and demo containers added to Docker Compose | P4 |
| P5-2 | frontend-engineer | Dashboard: session list, live trust timeline with decision markers, channel breakdown, explanations, policy editor, incident report view | P5-1 contract |
| P5-3 | frontend-engineer | Live demo mode in the demo app and dashboard | P5-2 |
| P5-4 | qa-engineer | Scenario 5 (dashboard shows decision and explanation) and demo reliability script | P5-1 to P5-3 |
| P5-5 | privacy-reviewer | Review | all P5 |

Parallel: P5-1 and P5-2.

### P6: Full evaluation and final report (weeks 13 to 14)

Success criterion (proposal): **All Section 13 core metrics reported with confidence intervals.**
Measured by: `docs/evaluation_report.md` containing FAR, FRR, EER, ROC-AUC, time-to-detect, bot and replay detection rate, scoring latency p50 and p95, robustness under drift, robustness under population-statistics attack, privacy cost of key categories, mouse versus touchpad and user friction, each with confidence intervals and the dataset sizes actually used. Metrics that need volunteer data and lack it are marked "not measured", never estimated.

| ID | Agent | Task | Depends on |
|---|---|---|---|
| P6-1 | backend-engineer | Latency instrumentation and a replay harness that feeds recorded volunteer sessions through the live pipeline | P5 |
| P6-2 | ml-engineer | Evaluation pipeline for every Section 13 core metric | P6-1 |
| P6-3 | orchestrator | `docs/evaluation_report.md`, final `README.md` | P6-2 |
| P6-4 | privacy-reviewer | Final review | all |

## Interfaces between agents

All defined in `docs/interfaces.md`:

| Interface | Producer | Consumers | Section |
|---|---|---|---|
| Session and stream handshake | backend (collector) | policy (demo backend), frontend, sdk | 4 |
| Event schema | sdk | backend | 5 |
| Batch format and signing | sdk | backend | 6 |
| Redis keys and streams | backend | backend worker, policy | 7 |
| Feature vector schema and window store | backend | ml | 8 |
| Channel score, profile template, trust update | ml | backend worker, policy, frontend | 9 |
| Bot and replay flags | policy | policy engine, frontend | 10 |
| Decision record and session control API | policy | demo backend, frontend, qa | 11 |
| Admin API and WebSocket | backend | frontend, qa | 13 |

## Risks

1. **Volunteer dataset.** The P3 criterion, the touchpad results in P2 and the headline numbers in P6 depend on 20 to 25 volunteers completing 6 sessions over at least 3 days. Collection needs consent forms and any ethics approval the institution requires, and should start as soon as P0 is done. Without it, those results will be reported as not measured.
2. **Docker Desktop** must be running for integration and end-to-end tests.
3. **OneDrive** syncs this folder. `node_modules`, `.venv` and Playwright output may slow syncing or hit file locks; pausing sync during installs helps.
4. **Aalto dataset size.** The full dataset is several gigabytes; a documented subset of users is used.
5. **Python 3.14** is recent; if a package lacks a wheel, the fallback is a `python:3.12` container, which would be raised with the owner first.
