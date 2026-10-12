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
| P1-1 | P1 | backend-engineer | todo | no | `kf-1` extraction, windowing, worker, retention |
| P1-2 | P1 | ml-engineer | todo | no | CMU, Aalto, metrics, baselines |
| P1-3 | P1 | ml-engineer | todo | no | Category versus key-pair experiment |
| P1-4 | P1 | privacy-reviewer | todo | n/a | |
| P2-1 | P2 | backend-engineer | todo | no | `pf-1`, `if-1` extraction and windowing |
| P2-2 | P2 | ml-engineer | todo | no | Balabit, SapiMouse, pointer models |
| P2-3 | P2 | ml-engineer | todo | no | Templates, enrollment, runtime scorers |
| P2-4 | P2 | backend-engineer | todo | no | Profiles table and enrollment trigger |
| P2-5 | P2 | privacy-reviewer | todo | n/a | |
| P3-1 | P3 | ml-engineer | todo | no | Fusion, trust update, insufficient signal |
| P3-2 | P3 | backend-engineer | todo | no | Worker wiring, `trust_points`, pub/sub |
| P3-3 | P3 | privacy-reviewer | todo | n/a | |
| P4-1 | P4 | policy-engineer | todo | no | Policy engine, decisions, session control API |
| P4-2 | P4 | policy-engineer | todo | no | Bot and replay heuristics |
| P4-3 | P4 | policy-engineer | todo | no | Demo backend TOTP and high-risk actions |
| P4-4 | P4 | frontend-engineer | todo | no | Demo frontend step-up and termination; also show a notice when `withdrawal_pending` is true |
| P4-5 | P4 | qa-engineer | todo | no | Playwright scenarios 1 to 4 |
| P4-6 | P4 | ml-engineer | todo | no | Synthetic attack generator |
| P4-7 | P4 | privacy-reviewer | todo | n/a | |
| P5-1 | P5 | backend-engineer | todo | no | Admin API, WebSocket, app containers |
| P5-2 | P5 | frontend-engineer | todo | no | Dashboard |
| P5-3 | P5 | frontend-engineer | todo | no | Live demo mode |
| P5-4 | P5 | qa-engineer | todo | no | Scenario 5, demo reliability |
| P5-5 | P5 | privacy-reviewer | todo | n/a | |
| P6-1 | P6 | backend-engineer | todo | no | Latency instrumentation, replay harness |
| P6-2 | P6 | ml-engineer | todo | no | Full evaluation |
| P6-3 | P6 | orchestrator | todo | n/a | Evaluation report, final README |
| P6-4 | P6 | privacy-reviewer | todo | n/a | |
