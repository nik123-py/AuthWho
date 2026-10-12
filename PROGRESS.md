# AuthWho progress

Status values: todo, in progress, review, done, blocked. "Tests passing" is recorded only after the orchestrator has run the suite itself.

| ID | Phase | Agent | Status | Tests passing | Notes |
|---|---|---|---|---|---|
| S1 | setup | orchestrator | done | n/a | Skills copied unchanged into `.claude/skills/` |
| S2 | setup | orchestrator | done | n/a | Seven agents in `.claude/agents/` |
| S3 | setup | orchestrator | done | n/a | Plan, interfaces and dependencies approved 2026-10-09; rulings R4 to R9 accepted without objection |
| P0-1 | P0 | orchestrator | done | n/a | Root config, `.venv` and npm workspaces installed, README |
| P0-2 | P0 | sdk-engineer | done | yes | 121 Vitest tests, typecheck, build verified; jsdom end-to-end capture against live collector showed categories only |
| P0-3 | P0 | backend-engineer | done | yes | Collector, compose, migrations, dump tool, session end; 304 Python tests verified 2026-10-12 |
| P0-4 | P0 | backend-engineer | done | yes | Encrypted research export, consent-time filter, verified deletion |
| P0-5 | P0 | policy-engineer | done | yes | 102 tests; withdrawal retry incl. background task. Follow-up for P5: login token expiry and Secure cookie |
| P0-6 | P0 | frontend-engineer | done | yes | 96 Vitest tests, typecheck, build verified; not yet viewed in a real browser |
| P0-7 | P0 | qa-engineer | done | n/a | Workflow checked locally; runs once the repo has a GitHub remote |
| P0-8 | P0 | privacy-reviewer | done | n/a | First review FAIL (withdrawal), re-review PASS 2026-10-12 |
| P1-1 | P1 | orchestrator | done | yes | `kf-1` (35 features), windower, `server.worker`, `windows` table, 30-day retention, withdrawal deletes windows; 393 Python tests verified 2026-10-12 |
| P1-2 | P1 | orchestrator | done | yes | Metrics, four JSON-serialisable detectors, CMU standard protocol (scaled Manhattan EER 0.0962 vs published 0.096); Aalto subset fetcher via HTTP range requests (500 participants, seed 0) |
| P1-3 | P1 | orchestrator | done | yes | Category vs key-pair: CMU cost +0.053 to +0.069 EER (CI excludes 0); Aalto cost -0.022 to -0.003 (categories as good or better). `experiments/results/category_vs_keypair.md` |
| P1-4 | P1 | orchestrator | done | n/a | Privacy review by orchestrator (no subagents): worker logs counts only, windows encrypted, Aalto text discarded at parse, `data/` gitignored. PASS |
| P2-1 | P2 | orchestrator | done | yes | `pf-1` (22) and `if-1` (17) extractors and windowers; worker windows all three channels with per-channel opt-outs |
| P2-2 | P2 | orchestrator | done | yes | Balabit (10 users) and SapiMouse (120) with live `pf-1`: best EER 0.163 Balabit, 0.158 SapiMouse at 30 strokes. Touchpad not measured (no labelled data) |
| P2-3 | P2 | orchestrator | done | yes | `ml/profile.py`: JSON templates, per-user calibrated scores with a far-tail decay, top deviating features |
| P2-4 | P2 | orchestrator | done | yes | `profiles` and `trust_points` (migration 0005), encrypted templates, enrollment at `AUTHWHO_ENROLL_WINDOWS` (default 20), deletion on withdrawal |
| P2-5 | P2 | orchestrator | done | n/a | Privacy self-review: templates encrypted with profile id as AAD; trust points hold scores and feature names only; logs hold counts |
| P3-1 | P3 | orchestrator | done | yes | `ml/trust.py` penalty-reward fusion with insufficient-signal state; chimeric users: fused EER 0.089 vs keystroke 0.144, pointer 0.197. Volunteer-data criterion not measurable yet |
| P3-2 | P3 | orchestrator | done | yes | Worker scoring stage, trust points, `aw:trust` publish, staleness tick. Live SDK test: genuine trust 100, takeover below 50 after 7 windows |
| P3-3 | P3 | orchestrator | done | n/a | Privacy self-review PASS |
| P4-1 | P4 | orchestrator | done | yes | Policy engine (5 levels, R6), decisions table append-only by trigger with 90-day retention, policies table, session control API, background policy monitor in the worker |
| P4-2 | P4 | orchestrator | done | yes | Bot and replay checks; no false flags on 7,078 Aalto and 776 SapiMouse windows; speed flag medium only (1.3% of Balabit windows) |
| P4-3 | P4 | orchestrator | done | yes | Demo backend: TOTP (pyotp, encrypted secret) or password step-up, three tries, policy check on high-risk actions, status check on every request |
| P4-4 | P4 | orchestrator | done | yes | Demo frontend: step-up dialog (event and 5 s status poll), session-ended page, authenticator setup, withdrawal-pending notice; 104 Vitest tests |
| P4-5 | P4 | orchestrator | done | yes | Playwright (Chromium) against the full stack: 5 scenarios pass in about 3 minutes; CI `e2e` job added |
| P4-6 | P4 | orchestrator | todo | no | Population-statistics synthetic attack generator moved to P6 (needed for the robustness metric) |
| P4-7 | P4 | orchestrator | done | n/a | Privacy self-review PASS: no scores shown to the operator, TOTP secret encrypted, logs hold no passwords, codes or scores |
| P5-1 | P5 | backend-engineer | todo | no | Admin API, WebSocket, app containers |
| P5-2 | P5 | frontend-engineer | todo | no | Dashboard |
| P5-3 | P5 | frontend-engineer | todo | no | Live demo mode |
| P5-4 | P5 | qa-engineer | todo | no | Scenario 5, demo reliability |
| P5-5 | P5 | privacy-reviewer | todo | n/a | |
| P6-1 | P6 | backend-engineer | todo | no | Latency instrumentation, replay harness |
| P6-2 | P6 | ml-engineer | todo | no | Full evaluation |
| P6-3 | P6 | orchestrator | todo | n/a | Evaluation report, final README |
| P6-4 | P6 | privacy-reviewer | todo | n/a | |
