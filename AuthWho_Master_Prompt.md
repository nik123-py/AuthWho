# AuthWho — Master Build Prompt for Claude Code (Multi-Agent Orchestration)

> **How to use this file:** create an empty folder (recommended:
> `C:\Users\05nik\OneDrive\Desktop\aakriti maam project\authwho`), open Claude Code in that
> folder, and paste everything below the line `=== PROMPT START ===` as your first message.
> You can also say: "Read `../AuthWho_Master_Prompt.md` and execute it."

=== PROMPT START ===

## 0. Your role

You are the **lead orchestrator and principal engineer** for **AuthWho**, a continuous
behavioural biometric authentication engine for web sessions. You do not write most of the code
yourself. You:

1. turn the proposal into a binding spec and a set of shared contracts,
2. break the work into tasks with clear file ownership,
3. **spawn one specialised subagent per domain** (ML, cybersecurity, backend, frontend, DevOps,
   QA, research/evaluation, and so on) using the Agent tool,
4. review each subagent's output against the spec, merge it, and keep a ledger,
5. make sure the end result runs with one command, passes its tests, and demos live.

**Problem statement (hackathon):**
> *Biometric Continuous Behavioural Authentication: Moving past static multi-factor
> authentication to continuously verify user identity via typing cadence, mouse movements, and
> cognitive interaction patterns.*

**Source of truth:** `C:\Users\05nik\OneDrive\Desktop\aakriti maam project\AuthWho_Project_Proposal-1.pdf`.
Read the whole PDF before doing anything else. When this prompt and the PDF disagree, the PDF
wins on *what* to build and this prompt wins on *how* to build it. Record every such conflict
as a ruling in the ledger (section 4.3).

---

## 1. Skills you must use

The skills are in `C:\Users\05nik\OneDrive\Desktop\nextgenai hackathon\hackathon_claude_skills\`.
They are not installed yet. **First action after `git init`:** copy them into the project so
Claude Code and every subagent can discover them:

```
.claude/skills/brainstorming/                    <- Superpowers/brainstorming
.claude/skills/writing-plans/                    <- Superpowers/writing-plans
.claude/skills/executing-plans/                  <- Superpowers/executing-plans
.claude/skills/subagent-driven-development/      <- Superpowers/subagent-driven-development
.claude/skills/dispatching-parallel-agents/      <- Superpowers/dispatching-parallel-agents
.claude/skills/test-driven-development/          <- Superpowers/test-driven-development
.claude/skills/systematic-debugging/             <- Superpowers/systematic-debugging
.claude/skills/verification-before-completion/   <- Superpowers/verification-before-completion
.claude/skills/requesting-code-review/           <- Superpowers/requesting-code-review
.claude/skills/receiving-code-review/            <- Superpowers/receiving-code-review
.claude/skills/using-git-worktrees/              <- Superpowers/using-git-worktrees
.claude/skills/finishing-a-development-branch/   <- Superpowers/finishing-a-development-branch
.claude/skills/frontend-design/                  <- frontend-design
.claude/skills/webapp-testing/                   <- webapp-testing
```

Copy each skill folder whole, including its helper files (`implementer-prompt.md`,
`task-reviewer-prompt.md`, `code-reviewer.md`, scripts and so on). `Superpowers/SKILL.md` and
`GSD/SKILL.md` are one-line stubs with no frontmatter. Do not install them; apply the GSD idea
yourself (keep your own context small by giving work to isolated agents).
`webapp-testing` mentions `scripts/with_server.py`, but that file is missing. Start servers
through Docker Compose or a small script you write.

### When to use each skill

| Moment | Skill | Who uses it |
|---|---|---|
| Before any design work | `brainstorming` → produce `docs/spec/AuthWho-SPEC.md` | Orchestrator |
| Spec → task list | `writing-plans` → `docs/plan/AuthWho-PLAN.md` | Orchestrator |
| Running the plan | `subagent-driven-development` (one implementer per task plus a task reviewer) | Orchestrator |
| Independent tasks in the same wave | `dispatching-parallel-agents` | Orchestrator |
| Parallel code changes | `using-git-worktrees` (Agent tool `isolation: "worktree"`) | Orchestrator |
| Writing any production code | `test-driven-development`: write a failing test first, then make it pass | Every implementer |
| Any bug or failing test | `systematic-debugging`: find the root cause before fixing | Every implementer |
| Before claiming "done" | `verification-before-completion`: run the commands and paste the output | Everyone |
| After each task or wave | `requesting-code-review` / `receiving-code-review` | Orchestrator plus reviewer agent |
| Dashboard, demo app, privacy page | `frontend-design` | Frontend agents |
| Browser E2E checks | `webapp-testing` (Python Playwright) | QA agent |
| End of project | `finishing-a-development-branch` | Orchestrator |

---

## 2. Non-negotiable invariants

Every agent gets this list word for word. If any one of these is broken, the work is rejected.

1. **No character content is ever captured, sent, logged or stored.** The SDK never reads
   `event.key`, `event.char`, input values or clipboard contents. It may read `event.code` only
   inside the SDK, to map the key to a coarse **key category** and a **keyboard zone**, and must
   then discard the code. Tests must prove this (section 9).
2. **Password and sensitive fields capture nothing** beyond "a sensitive field was focused".
   Timing inside a password field leaks length and rhythm, so it is suppressed completely.
3. **"Insufficient signal" is a first-class outcome.** When there is too little evidence, the
   system outputs `CANNOT_DETERMINE` and falls back to normal session rules. It never guesses.
4. **The model never acts on its own.** Models return `{score, confidence}`. Only the policy
   engine decides, and every decision is stored with its evidence: channels, top features,
   deviation sizes, window ids and model version.
5. **Scoring is asynchronous and off the request path.** The protected app never waits for ML.
6. **Profiles are templates, not raw events.** They are encrypted at rest (AES-256-GCM, one data
   key per user), versioned, and fully deletable. Deleting the key destroys the data
   (crypto-shredding).
7. **Profiles update only from verified sessions** (passed step-up or otherwise confirmed), with
   a cap on how far one update can move the profile. Sustained drift raises an alert.
8. **The trust score is never shown to the end user or operator** of the protected session. It
   appears only on the admin dashboard. This is the defence against mimicry (Tey et al.).
9. **The audit log is append-only and hash-chained**, and a verify endpoint proves no record
   was changed.
10. **Zero cost and zero special hardware.** Everything uses free open-source software, runs on
    one Windows laptop with Docker Desktop, and needs only a keyboard and a mouse or touchpad.
11. **Secrets live only in `.env` files that are git-ignored.** A `.env.example` lists every
    variable.
12. **Every metric reported must be reproduced by a committed script** with a fixed seed. Never
    invent or round up numbers. If a target is missed, report the real number.

---

## 3. Target architecture (binding)

```
Browser SDK (TypeScript)  ── timings + motion + categories, NO characters
   │  HTTPS / WebSocket, HMAC-signed, sequence-numbered batches
   ▼
collector-api (FastAPI)  ── auth, schema validation, rate limit, nonce/seq/skew checks
   ├──► PostgreSQL (sessions, event metadata, policies, decisions, audit, profiles[enc])
   ▼
Redis Streams  events:{tenant}
   ▼
pipeline-worker (Python)
   ├─ windowing (action-count windows, overlapping)
   ├─ feature extraction (keystroke / mouse / interaction)
   ├─ per-user scorers (ONNX Runtime + sklearn)    ◄── Profile Store (encrypted, versioned)
   ├─ bot / replay / synthetic detector (independent of user model)
   ├─ trust fusion engine (penalty-reward + confidence + CANNOT_DETERMINE)
   └─ policy engine (trust × confidence × action sensitivity → decision)
           ├─► Keycloak step-up (OIDC, acr / max_age=0)
           ├─► session manager (continue / step-up / terminate via Redis session state)
           └─► hash-chained audit log
   ▼
collector-api WebSocket ──► Admin Dashboard (React + TS + Recharts)
MLflow (model registry) · Prometheus + Grafana (latency, lag, drops, step-up rate, errors)
Demo app "Ledgerly" (fictional bank) embeds the SDK and guards its high-risk actions with AuthWho.
```

**Pragmatic ruling (already made, do not reopen):** run as **three Python processes**:
`collector-api`, `pipeline-worker` and `trainer` (an offline CLI). Inside the worker,
features, scoring, fusion and policy are **separate packages with separate tests**. This
satisfies the PDF's "independently replaceable" requirement without six containers on a laptop.

### 3.1 Repository layout

```
authwho/
  contracts/            # JSON Schemas + OpenAPI; single source of truth for all agents
  sdk/                  # TypeScript browser SDK (Vite library build, Vitest)
  services/
    common/             # pydantic models generated from contracts/, crypto, config, logging
    collector_api/      # FastAPI app: ingest, query API, WebSocket, step-up callbacks
    pipeline/
      windowing/  features/  scoring/  detectors/  fusion/  policy/  audit/  profiles/
    trainer/            # CLI: enroll, train, export ONNX, register in MLflow
  ml/
    datasets/           # loaders + download scripts (CMU, Balabit, SapiMouse, Aalto subset)
    keystroke/  mouse/  interaction/  fusion_eval/  attacks/  reports/
  dashboard/            # React + Vite + TS admin console
  demo-app/             # "Ledgerly" fictional bank (React or plain Vite) using the SDK
  infra/
    docker-compose.yml  keycloak/realm-export.json  prometheus/  grafana/  postgres/init.sql
  tests/
    e2e/                # Python Playwright (webapp-testing skill)
    replay/             # recorded-session replay tests
  docs/
    spec/  plan/  adr/  threat-model.md  privacy.md  eval-report.md  demo-script.md  ledger.md
  .github/workflows/ci.yml
  Makefile (or justfile)  .env.example  README.md
```

**Toolchain:** Python 3.11 with `uv` (or pip plus `requirements.lock`), ruff, mypy and pytest.
Node 20 with pnpm, TypeScript strict mode, ESLint, Vitest and Vite. Docker Compose v2.
The machine runs Windows, so every script needs a cross-platform entry point (Makefile targets
that call Python or Node, never bash-only).

---

## 4. Orchestration protocol

### 4.1 Startup sequence (do these in order, yourself)

1. `git init`, add `.gitignore` (node_modules, .venv, .env, data/raw, mlruns, *.onnx except
   fixtures), then copy the skills (section 1).
2. Read the PDF completely. Load `brainstorming` and write `docs/spec/AuthWho-SPEC.md`. It must
   cover: scope, the out-of-scope list, personas (admin, end user, attacker), the invariants,
   the architecture, the trust bands, the policy matrix, data contracts, evaluation targets and
   the demo story. This is a hackathon, so make reasonable decisions yourself instead of asking
   many questions. Ask the user only about things that are genuinely theirs to decide, such as
   team members' names on the consent form.
3. **Spawn the Architect agent (A0)** to write `contracts/` (section 5). Every later agent
   depends on these, so wait for A0, review its work and freeze the contracts (tag
   `contracts-v1`). After that, a contract changes only through an ADR in `docs/adr/`.
4. Load `writing-plans` and write `docs/plan/AuthWho-PLAN.md`: tasks grouped into the waves in
   section 6, each with an owner agent, the files it owns, dependencies, acceptance tests and a
   "done" command.
5. Run the waves using `subagent-driven-development` plus `dispatching-parallel-agents`.

### 4.2 Spawning rules

- Use the **Agent tool**. Code-writing agents use `subagent_type: "general-purpose"` with
  `isolation: "worktree"`. Pure design or architecture agents use `subagent_type: "Plan"`.
  Codebase searches use `subagent_type: "Explore"`.
- Run **no more than 4 code-writing agents at once**, to limit merge conflicts and laptop load.
- **File ownership is exclusive within a wave.** Two agents in the same wave never edit the same
  path. Shared files (`contracts/`, `docker-compose.yml`, root configs) belong to one owner,
  and other agents request changes in their final report.
- Every subagent prompt follows the template in section 8. Never assume a subagent has seen
  this conversation. Give it the invariants, the relevant contract files, its task, the files
  it owns, the skills it must use, its acceptance criteria and the exact verification commands.
- After each implementer finishes, spawn a **reviewer agent** (use
  `Superpowers/requesting-code-review/code-reviewer.md` and
  `subagent-driven-development/task-reviewer-prompt.md`) that checks **spec compliance** first
  and **code quality** second. Follow the fix-round rules in `subagent-driven-development`.
- The **Security Reviewer (A8b)** reviews every change that touches the SDK, transport, auth,
  crypto, the audit log or profiles before it is merged.
- Merge each worktree into `main` only after its tests pass on `main` after the merge. Never
  push to a remote or publish anything without asking the user.

### 4.3 Ledger

Keep `docs/ledger.md` up to date with: the wave and task status table, which agent is on which
task, every ruling in the form `Ruling: <decision> — <why> — <cost if wrong>`, open risks, and
the metrics measured so far. Keep chat narration to one line between tool calls; put detail in
the ledger.

### 4.4 When to stop and ask the user

Stop only for: destructive or irreversible operations, pushing or publishing outside the repo,
anything that would collect real personal data before a consent form exists, downloads larger
than about 5 GB, or a spec defect where every path forward is a guess. Decide everything else
and record the ruling.

---

## 5. Shared contracts (A0 writes these first; everyone builds against them)

A0 writes JSON Schema (draft 2020-12) files in `contracts/`, generates pydantic v2 models into
`services/common/` and TypeScript types into `sdk/src/types/`, and adds a CI check that the
generated code matches the schemas.

### 5.1 `event-batch.schema.json` (SDK → collector)

```jsonc
{
  "session_id": "uuid",
  "tenant_id": "string",
  "seq": 42,                       // strictly increasing per session
  "nonce": "base64(16 bytes)",
  "sent_at": 1730000000123.4,      // ms, performance.timeOrigin + performance.now()
  "sdk_version": "1.0.0",
  "page": { "route_id": "transfer", "sensitivity": "high" },   // route id, never full URL with query
  "events": [
    { "t": 1234.56, "type": "kd", "cat": "letter", "zone": "L2" },   // keydown
    { "t": 1301.02, "type": "ku", "cat": "letter", "zone": "L2" },   // keyup
    { "t": 1400.00, "type": "mm", "x": 512, "y": 300, "pt": "mouse" },// pointer move (coalesced)
    { "t": 1410.00, "type": "md", "btn": 0, "x": 515, "y": 302 },     // mouse down
    { "t": 1490.00, "type": "mu", "btn": 0, "x": 515, "y": 302 },
    { "t": 1500.00, "type": "wh", "dy": 120 },                        // wheel/scroll
    { "t": 1600.00, "type": "fc", "target": "field:amount", "sens": false }, // focus change (field role id, no value)
    { "t": 1700.00, "type": "nav", "route_id": "add_payee" },
    { "t": 1800.00, "type": "clip", "op": "paste" },                  // op only, never content
    { "t": 1900.00, "type": "vis", "state": "hidden" },               // tab visibility
    { "t": 2000.00, "type": "trust_flag", "untrusted": true }         // event.isTrusted === false seen
  ],
  "sig": "base64(HMAC-SHA256(session_key, canonical_json(batch_without_sig)))"
}
```

- `cat` ∈ `letter | digit | space | backspace | delete | enter | tab | modifier | arrow |
  punctuation | other`.
- `zone` is the hand and row of the physical key: `L0..L3`, `R0..R3`, `T` (thumb/space), `X`
  (unknown). It is computed in the SDK from `event.code` with a static map. `zone` is omitted
  for `modifier` and `other`. **Ruling:** zones allow digraph-*like* features (same-hand vs
  alternating-hand transitions, row jumps) without revealing which characters were typed.
  A0 must justify in an ADR that zone sequences cannot practically be used to rebuild text.
- Coordinates are viewport CSS pixels. Pointer moves are coalesced so that each move event is
  at least 8 ms apart, but raw `getCoalescedEvents()` timing is used for the velocity features.

### 5.2 `feature-window.schema.json`

`{window_id, session_id, user_id, channel: "keystroke"|"mouse"|"interaction", start_t, end_t,
n_actions, features: {name: float}, quality: {n_events, idle_ratio, coverage}}`

### 5.3 `channel-score.schema.json`

`{window_id, channel, model_id, model_version, score ∈ [0,1] (1 = genuine-like),
confidence ∈ [0,1], top_features: [{name, z, direction}], status: "ok"|"insufficient"|"no_model"}`

### 5.4 `trust-state.schema.json`

`{session_id, t, trust ∈ [0,100], confidence ∈ [0,1], band:
"HIGH"|"MODERATE"|"STRONG_DEVIATION"|"CRITICAL"|"CANNOT_DETERMINE", channel_contrib:
{keystroke, mouse, interaction}, flags: ["bot_suspected","replay_suspected","population_like",...]}`

### 5.5 `decision.schema.json`

`{decision_id, session_id, t, action_requested?, action_sensitivity, outcome:
"CONTINUE"|"MONITOR"|"STEP_UP"|"BLOCK_AND_TERMINATE"|"FALLBACK_NORMAL", trust_state,
evidence: {windows: [...], top_features: [...], detector_flags: [...]}, policy_version,
model_versions, explanation_text, prev_hash, hash}`

### 5.6 APIs (OpenAPI in `contracts/openapi.yaml`)

- `POST /v1/session/start`: called after the app's own login. Returns `session_id`, a per-session
  HMAC `session_key` and the SDK config (window sizes, capture flags).
- `POST /v1/events` and `WS /v1/events/ws`: batch ingest. Returns `202` with
  `{accepted, last_seq}` or `4xx` with a reason code.
- `POST /v1/authorize`: the app asks before a sensitive action:
  `{session_id, action: "add_payee"}` → `{outcome, step_up_url?, decision_id}`. This must answer
  from **cached trust state in Redis in under 20 ms p95**. It never runs ML inline.
- `POST /v1/stepup/callback`: Keycloak OIDC return. Marks the session as verified and unlocks
  profile updates.
- `GET /v1/sessions`, `GET /v1/sessions/{id}/timeline`, `GET /v1/decisions/{id}`,
  `GET /v1/audit/verify`, `GET|PUT /v1/policies`, `POST /v1/users/{id}/enroll`,
  `DELETE /v1/users/{id}/profile` (crypto-shred), `GET /v1/incidents/{session_id}/report`
  (JSON plus printable HTML).
- `WS /v1/admin/live`: pushes trust states and decisions to the dashboard. Requires an admin
  OIDC token.

---

## 6. Waves, agents and tasks

Each agent card below is the **seed** for its subagent prompt. Expand it with the section 8
template. "Owns" means the agent has exclusive write access to those paths during its wave.

### Wave 0: Foundations (sequential)

**A0 — Architect / Contracts** (`Plan` agent for design, then `general-purpose` to write files)
- Owns: `contracts/`, `services/common/` (generated models), `sdk/src/types/`, `docs/adr/0001-*`.
- Tasks: all schemas and OpenAPI from section 5; codegen scripts; contract tests (valid and
  invalid fixtures for every schema); the zone-privacy ADR; and ADR-0002 on the three-process
  topology.
- Done when: `make contracts-check` passes, there are at least 3 valid and 3 invalid fixtures
  per schema, and the generated TS and Python types compile.

**A1 — DevOps scaffold**
- Owns: `infra/`, `docker-compose.yml`, `Makefile`, `.env.example`, `.github/workflows/ci.yml`,
  root lint configs.
- Tasks: Compose services `postgres:16`, `redis:7`, `keycloak` (quay.io/keycloak, dev mode,
  realm import `authwho` with clients `ledgerly`, `authwho-dashboard`, test users and a TOTP
  step-up flow), `mlflow`, `prometheus`, `grafana` (provisioned datasource and an empty
  dashboard), plus placeholders for `collector-api`, `pipeline-worker`, `dashboard` and
  `demo-app`. Health checks on every service. `make up`, `make down`, `make test`, `make lint`,
  `make seed`. CI runs lint, unit tests, contract checks and the docker build.
- Done when: `make up` brings every infra service to healthy on Windows and Docker Desktop, and
  CI passes on a dummy commit.

### Wave 1: Capture and ingest (parallel, up to 4 agents)

**A2 — Browser SDK engineer (TypeScript)**
- Owns: `sdk/`.
- Tasks:
  - Listeners: `keydown`, `keyup`, `pointermove` (with `getCoalescedEvents`), `pointerdown`,
    `pointerup`, `wheel`, `focusin`, `focusout`, `visibilitychange`, `paste`, `copy`, `cut`
    (operation only), and route changes through an `AuthWho.setRoute(id, sensitivity)` API.
  - Category and zone mapper from `event.code`. **Never touch `event.key`.** Add a lint rule
    (ESLint `no-restricted-properties`) that bans `.key`, `.value`, `.char`, `.charCode`,
    `.keyCode`, `.which`, `clipboardData` and `innerText` reads in `sdk/src`.
  - Sensitive-field detection: `input[type=password]`, `autocomplete` values containing
    `password`, `cc-`, `one-time-code`, or a `data-authwho-sensitive` attribute. Inside these
    fields only `fc` events with `sens: true` are sent.
  - Batching every 2 s or every 200 events, whichever comes first; HMAC-SHA256 via WebCrypto;
    strictly increasing `seq`; random nonce; a retry queue with exponential backoff that keeps
    order; at most 1 MB of memory; a `beacon` flush on `pagehide`.
  - Flag `isTrusted === false` events (`trust_flag`) without dropping them.
  - Public API: `AuthWho.init({endpoint, sessionId, sessionKey})`, `setRoute`, `setUser`,
    `pause`, `resume`, `destroy`, `onStatus(cb)`. Gzipped size under 15 KB. No runtime
    dependencies.
  - Optional (P2 stretch): compute keystroke features in the browser (the PDF says "where
    practical") behind a flag.
- Tests: Vitest with jsdom. Simulate typing a known sentence and assert that the serialized
  batch **contains none of its characters** (fuzz with 1,000 random strings, including Unicode
  and Hindi). Also test sensitive-field suppression, ordering and signature validity.
- Skills: `test-driven-development`, `verification-before-completion`.

**A3 — Backend engineer: collector-api (FastAPI)**
- Owns: `services/collector_api/`, `services/common/` (non-generated parts: config, db, redis,
  logging, metrics).
- Tasks: every endpoint in 5.6 (stubs return 501 until their wave); SQLAlchemy 2 plus Alembic
  migrations; ingest pipeline steps: validate against the schema → check `seq` is strictly
  greater than `last_seq` → check the nonce has not been seen in Redis (TTL 10 min) → check
  `|sent_at − server_now| < 120 s` (with a session clock-offset estimate) → verify HMAC with
  `hmac.compare_digest` → `XADD events:{tenant}`. Rate limit per session and per IP (token
  bucket in Redis). Body limit 256 KB. Reject keys outside the schema
  (`additionalProperties: false`). Prometheus metrics: `ingest_batches_total{result}`,
  `ingest_latency_seconds`, `stream_lag`. Structured JSON logs that never include an event
  payload.
- Tests: pytest with httpx AsyncClient and testcontainers (or the Compose services). A replayed
  batch, a reordered batch, a tampered signature, a stale timestamp, a body that is too large
  and an unknown field must each be rejected with a distinct reason code.

**A4 — Data engineer: datasets and loaders**
- Owns: `ml/datasets/`, `data/` (git-ignored, apart from small fixtures).
- Tasks:
  - **CMU Keystroke** (`DSL-StrongPasswordData.csv`, https://www.cs.cmu.edu/~keystroke/): loader
    giving per-subject H/DD/UD vectors.
  - **Balabit Mouse Dynamics Challenge** (github.com/balabit/Mouse-Dynamics-Challenge): parse
    sessions; segment into strokes (split on pauses longer than 300 ms or on clicks) and
    actions (Mouse Move / Point-Click / Drag-Drop, as in Ahmed & Traore); use
    `public_labels.csv` for test sessions.
  - **SapiMouse** (from the Antal et al. paper): 1-minute and 3-minute sessions, the same stroke
    segmentation.
  - **Aalto 136M keystrokes**: write a script that downloads a **subset** (for example 2,000
    users) and converts it to the SDK's category and zone format, so the free-text keystroke
    model trains on data shaped like live data. If the full archive is larger than 5 GB, ask
    before downloading.
  - **Consented volunteer dataset**: a `ml/datasets/consented/` loader for SDK-captured
    sessions exported from Postgres, plus `docs/consent-form.md` (plain language: what is and
    is not collected, how to withdraw, how data is deleted, references to DPDP Act 2023 and
    GDPR Art. 9) and a `collection-protocol.md` (for example 3 enrollment sessions of 10 minutes
    each on Ledgerly tasks, plus 2 test sessions on a different day, using anonymous ids).
  - A unified `Session → events DataFrame` interface so every model trains on the same shape.
    Write dataset cards (size, licence, citation, known biases).
- Tests: loaders return the expected subject and row counts on small committed fixtures.

**A11a — Frontend: dashboard shell** (can start in Wave 1 against mocked contracts)
- Owns: `dashboard/`.
- Load the `frontend-design` skill **before writing any UI**. Design direction: a calm,
  forensic security-operations console. Avoid the clichés the skill lists (cream with
  terracotta, black with neon green). Choose a distinctive typeface pair and a palette in
  which trust bands stay readable for colour-blind users (use shape and pattern as well as
  colour).
- Tasks: Vite, React and TS with React Router and Recharts; OIDC login against Keycloak; a mock
  WebSocket server that replays fixture trust states so UI work does not wait on the backend.
  Pages: **Sessions** (live list: user, app, trust, confidence, band, last decision),
  **Session detail** (trust and confidence timeline with decision markers and a shaded
  `CANNOT_DETERMINE` region; a channel-breakdown stacked area; top features at the selected
  moment; plain-language explanations), **Policies** (editor for per-app, per-role and
  per-action thresholds with validation and a version history), **Users and enrollment** (status
  and re-enroll), **Audit** (verify-chain button with the result), **Incident report** (export
  to printable HTML or PDF).

### Wave 2: Features and per-channel models (parallel)

**A5 — ML engineer: keystroke channel**
- Owns: `ml/keystroke/`, `services/pipeline/features/keystroke.py`,
  `services/pipeline/scoring/keystroke.py`.
- Features per window (default 50 keystrokes, stride 25): mean, std, median, IQR and p10/p90
  of **dwell** (ku−kd of the same key); **flight** in 4 forms (kd→kd, ku→kd, ku→ku, kd→ku);
  latencies for category pairs and zone-transition pairs (same-hand, alternating-hand,
  same-row, row-jump, digraph-like and trigraph-like); **rollover rate** (next kd before the
  previous ku); backspace rate and correction-burst rhythm (time from error to backspace,
  number of backspaces per burst); pause histogram (>500 ms, >2 s); typing speed (keys/s,
  excluding pauses).
- Models, in this order:
  1. **Reproduce Killourhy & Maxion on CMU** using the exact protocol: per subject, train on the
     first 200 repetitions; test on that subject's remaining 200 and on the first 5
     repetitions of each of the other 50 subjects. Implement Scaled Manhattan, Mahalanobis,
     One-Class SVM, GMM, Isolation Forest and an autoencoder. Report per-detector mean (±sd)
     EER. **Target: match or beat about 9.6% EER (Scaled Manhattan).**
  2. **Free-text model on the Aalto subset in category/zone format:** a TypeNet-style LSTM
     with triplet loss (PyTorch) giving a 128-d embedding, scored by distance to the user's
     enrollment centroid. Compare it with the one-class baselines on the same windows. Export
     to ONNX and check that the outputs match PyTorch within 1e-4.
  3. **Small-enrollment fallback:** if a user has fewer than N enrollment windows, use a
     one-class model (best from step 1); otherwise use the embedding model. This is the
     PDF's "one-class for small sets, embeddings for larger" rule.
- Score calibration: map the raw distance to `score ∈ [0,1]` per user using the enrollment
  distribution (empirical CDF or Platt scaling on held-out genuine and impostor data). Compute
  `confidence` from window quality (number of events and idle ratio).
- Every run is logged to MLflow (params, metrics, artifacts, model signature). Register models
  as `authwho-keystroke-{oneclass|typenet}`.

**A6 — ML engineer: mouse and interaction channels**
- Owns: `ml/mouse/`, `ml/interaction/`, the `features/mouse.py`, `features/interaction.py`,
  `scoring/mouse.py` and `scoring/interaction.py` modules.
- Mouse features per stroke and aggregated per window (default 30 strokes, stride 15):
  velocity (vx, vy, |v|) stats; acceleration and jerk; curvature and angle change; **efficiency
  = straight-line distance / path length**; time to max velocity; number of velocity peaks
  (sub-movements, a sign of micro-corrections); pause distribution before clicks; click dwell
  (md→mu); double-click interval; direction histogram (8 bins); drag-drop stats; the share of
  Move / Point-Click / Drag actions (Ahmed & Traore). Handle touchpad vs mouse (`pt`) as a
  feature or as separate user models.
- Models: one-class baselines plus a **1D-CNN encoder on raw stroke sequences** (dx, dy, dt,
  resampled to a fixed length) trained with triplet or contrastive loss, following SapiMouse.
  Evaluate on Balabit (official test labels) and SapiMouse (1-minute sessions). Report EER and
  ROC-AUC per user and averaged, and **EER as a function of the number of strokes** (Ahmed &
  Traore observed that more observation lowers error).
- Interaction ("cognitive") features: hesitation time before high-sensitivity actions (from
  `nav` and `fc`); form-filling order (an edit-distance-like comparison of field focus order
  against the user's usual order); tab and focus switching rate; scroll velocity and
  reading-pause pattern; paste usage on fields where the user normally types; time from route
  load to first interaction. Use a simple model (per-user z-scores or a one-class model).
  Interaction is **evidence-weighted low** in fusion until it is validated.
- Export ONNX, log to MLflow, register `authwho-mouse-*` and `authwho-interaction-*`.

**A7 — Backend/ML engineer: streaming pipeline**
- Owns: `services/pipeline/windowing/`, `services/pipeline/profiles/`, the
  `services/pipeline/worker.py` entry point, and `services/trainer/`.
- Tasks: a Redis Streams consumer group (`XREADGROUP`, ack after commit, a dead-letter stream
  after 3 failures, idempotent by `(session_id, seq)`); **action-count windows** per channel
  with overlap; window quality metrics; calling A5/A6 feature and scoring functions through a
  stable interface `score(window, profile) -> ChannelScore`; an ONNX Runtime session cache
  keyed by model version; writing scores and trust state to Redis (`trust:{session_id}`, TTL =
  session) and to Postgres (async batch inserts).
- Profile store: an AES-256-GCM envelope with a KEK from `.env` and a DEK per user; template =
  per-channel statistics, embedding centroid and covariance, calibration params, model version
  and enrollment window count; version history; `DELETE` destroys the DEK.
- `trainer` CLI: `enroll --user u --from-sessions ...`, `retrain-population`, `export-onnx`,
  `register`.
- Latency target: **p95 below 300 ms** from batch XADD to updated trust state on a laptop
  (measured and exported as `scoring_latency_seconds`).

**A8a — Security engineer: bot, replay and synthetic detector**
- Owns: `services/pipeline/detectors/`, `ml/attacks/` (shared with A16 later through an ADR if
  needed).
- These detectors are **independent of the user model** and produce flags plus a severity:
  - **Automation / bot:** coefficient of variation of inter-key intervals below a threshold
    (scripts are too regular); dwell times that are identical or quantised (for example
    multiples of 1 ms or 16.67 ms); `isTrusted=false` events; pointer jumps with physically
    impossible speed (for example above 10,000 px/s with no intermediate samples); perfectly
    straight or constant-velocity strokes; no sub-movements or overshoot before a click; clicks
    exactly at element centres many times in a row; keydown/keyup without any pointer activity
    over long form flows; zero entropy in timing.
  - **Replay of recorded behaviour:** keep a rolling store of hashed, quantised window
    fingerprints per user (locality-sensitive hashing over feature vectors, plus a DTW check
    on stroke shapes for candidates). A near-exact match to a past window (cosine similarity
    above 0.995 or DTW below ε) is flagged, because real humans never repeat themselves exactly.
  - **Population-statistics forgery** (Serwadda & Phoha): compare the distance to the user
    profile with the distance to the population mean (from Aalto). Flag windows that are
    suspiciously close to the population average *and* have the low variance typical of
    generated data.
  - Network replay is already blocked by A3's seq, nonce and HMAC checks. The detector
    double-checks per-session sequence continuity.
- Tests: unit tests with synthetic generators (see A16); measure the false-positive rate on
  genuine CMU, Balabit and SapiMouse windows, which must stay below 1%.

**A8b — Security engineer: threat model and security review** (runs from Wave 1 to the end)
- Owns: `docs/threat-model.md`, `docs/security-review/*.md`, `SECURITY.md`.
- Tasks: a STRIDE threat model covering every arrow in the architecture, including: an AiTM
  cookie thief, a shoulder-surfing insider, credential sharing, a RAT on the victim's machine,
  a bot or headless browser, a mimicry attacker (Tey), a synthetic attacker (Serwadda), a
  recorded-replay attacker, slow profile poisoning, a malicious SDK modifier (be explicit:
  **a client the attacker fully controls can forge events; HMAC protects transport, not the
  endpoint**, so the defences are the behavioural detectors plus step-up), dashboard XSS, IDOR
  on session and decision endpoints, WebSocket auth, JWT validation (iss, aud, exp, alg
  pinning), CSRF on policy edits, Keycloak misconfiguration, secret leakage, log injection, and
  DoS by event flooding.
- Reviews every PR that touches the SDK, collector, crypto, profiles, audit or auth. Runs
  `bandit`, `pip-audit`, `npm audit`, `semgrep --config p/owasp-top-ten` (all free) in CI. Write
  findings with severity and a fix, then verify each fix.
- Privacy review: data-flow diagram, data inventory ("what we collect" vs "what we never
  collect"), retention (raw events 7 days by default, then only features and templates),
  user rights (access and erase), DPDP Act 2023 and GDPR Arts. 4(14), 5(1)(c) and 9 mapping
  → `docs/privacy.md`.

### Wave 3: Trust, policy, step-up, audit (parallel)

**A9 — Trust fusion engineer**
- Owns: `services/pipeline/fusion/`, `ml/fusion_eval/`.
- **Per-channel evidence weight:** `w_c = conf_c × reliability_c`, where `reliability_c` comes
  from that channel's validation EER (better channels count more). Missing or insufficient
  channels get weight 0. **They are never imputed.**
- **Fused window score:** `s = Σ w_c s_c / Σ w_c` (if `Σ w_c` is below the evidence threshold
  → `CANNOT_DETERMINE`).
- **Running trust:** the Mondal & Bours penalty-and-reward rule:
  `T_i = clamp(T_{i-1} + ΔT(s_i), 0, 100)` with
  `ΔT(s) = min(−D + D·(1 + 1/C) / (1/C + exp(−(s − A)/B)), C)`, where A is the per-user score
  threshold, B the width, C the maximum reward and D the maximum penalty. **Check the formula
  against the paper** (Neurocomputing 230, 2017) and record the parameters in an ADR. Fit A, B,
  C and D on validation data to minimise time-to-detect subject to the genuine step-up rate.
  New sessions start at T₀ = 90 (MFA just passed).
- **Confidence:** grows with total effective evidence over the last 60 s (for example
  `1 − exp(−n_eff/n₀)`), is boosted when channels agree and reduced when they disagree, and
  decays during idle periods. `CANNOT_DETERMINE` when confidence < 0.35 or no channel was
  `ok` in the last 60 s; the trust value then freezes instead of drifting.
- **Bands** (defaults, editable in policy): HIGH ≥ 80; MODERATE 60–80; STRONG_DEVIATION 40–60
  or any `bot_suspected` / `replay_suspected` flag of medium severity; CRITICAL < 40 or
  confirmed automation.
- **Explanation generator:** a template-based sentence built from the top deviating features
  and their durations, for example *"Typing rhythm (flight time +2.8σ) and mouse speed (+3.1σ)
  both diverged from this user's profile for 40 seconds."* No LLM is needed. Keep it
  deterministic and testable.
- **Evaluation:** on the consented multi-channel dataset (and on synthetic pairings of CMU,
  Balabit and SapiMouse users if consented data is small; label that clearly as a proxy), show
  that **fusion beats each single channel**. Target: **EER below 5% within about 1 minute of
  active use**. Report time-to-detect (seconds and number of impostor actions, ANIA/ANGA in
  the style of Mondal & Bours).

**A10 — Policy engine, step-up and session manager**
- Owns: `services/pipeline/policy/`, `services/collector_api/routes/authorize.py`,
  `routes/stepup.py`, `infra/keycloak/` (shared with A1 through a handoff).
- Policy as versioned YAML or JSON in Postgres, evaluated by a pure function
  `decide(trust_state, action_sensitivity, policy) -> Decision`, with 100% branch coverage.
  Default matrix:

  | Band \ Action sensitivity | low | medium | high |
  |---|---|---|---|
  | HIGH | CONTINUE | CONTINUE | CONTINUE |
  | MODERATE | MONITOR | MONITOR (stricter A) | STEP_UP |
  | STRONG_DEVIATION | STEP_UP | STEP_UP | STEP_UP |
  | CRITICAL | BLOCK_AND_TERMINATE | BLOCK_AND_TERMINATE | BLOCK_AND_TERMINATE |
  | CANNOT_DETERMINE | FALLBACK_NORMAL | FALLBACK_NORMAL | FALLBACK_NORMAL (+ app's normal re-auth rule) |

- Step-up through Keycloak: OIDC authorization code with PKCE and `max_age=0` /
  `prompt=login` (or `acr_values` mapped to a TOTP level of assurance). On success, mark the
  session as verified, add a reward to trust (capped), and allow profile updates for windows
  after verification. On failure or timeout: `BLOCK_AND_TERMINATE` (revoke the Redis session,
  call the Keycloak backchannel logout, notify the app).
- Repeated-step-up damping: at most 1 prompt per 15 min for the same cause unless the band
  worsens. Track `stepup_prompts_total{user}` for the friction metric.
- Drift-aware profile update: an EMA on the template using only verified windows, a
  per-update movement cap (for example 5% of the per-feature std), and an alert when the
  cumulative movement over 7 days exceeds a threshold (to catch poisoning).

**A10b — Audit log engineer** (small task; can be bundled with A10 if capacity is short)
- Owns: `services/pipeline/audit/`, migration for `audit_log`.
- `hash = SHA-256(prev_hash ‖ canonical_json(record))`, with a genesis record; a Postgres role
  with INSERT and SELECT only; a trigger that raises on UPDATE and DELETE; `GET /v1/audit/verify`
  walks the chain and reports the first broken link; tests that tamper with a row as superuser
  and show that verify detects it.

### Wave 4: Product integration and attack simulation (parallel)

**A11b — Frontend: dashboard integration**
- Owns: `dashboard/`.
- Replace the mocks with the live API and WebSocket. Live trust timeline under 1 s behind
  events; incident report export; policy editor wired to `PUT /v1/policies`, which creates a new
  version that is also written to the audit log; a "What we collect" page that is public and
  readable by end users.
- Accessibility: keyboard navigation, ARIA labels on charts, colour-blind-safe bands.

**A12 — Frontend: demo app "Ledgerly" and live demo mode**
- Owns: `demo-app/`.
- Load `frontend-design`. Ledgerly is a **fictional** bank. It must not look like or name any
  real bank. Pages: login (Keycloak), accounts overview, transactions (scroll-heavy, to show
  `CANNOT_DETERMINE` while the user only reads), transfer (medium), **add payee (high)**,
  **export customer report (high)**, profile settings (high).
- Integrate the SDK; call `/v1/authorize` before high actions; handle STEP_UP by redirecting to
  Keycloak and returning; handle termination with a clear "session ended for your protection"
  screen.
- Enrollment flow: consent screen (from `docs/consent-form.md`) → guided tasks (typing a short
  paragraph, filling a form, a target-clicking exercise) → "profile ready" status.
- **Live demo mode:** a toggle that shows a split screen for evaluators: the Ledgerly session
  on the left and the dashboard timeline on the right. A "hand over the laptop" moment: the
  presenter types, then an evaluator takes over, and the audience watches trust fall and the
  step-up trigger. Add a **bot button** that runs the A16 Playwright bot against the same
  session.

**A16 — Red team: adversarial evaluation** (local stack only; never targets external systems)
- Owns: `ml/attacks/`, `tests/attacks/`, `docs/eval/robustness.md`.
- Build attack generators and measure detection on the running stack:
  1. **Scripted bot** (Playwright `keyboard.type` with a fixed delay, then with random jitter,
     then with jitter sampled from a population distribution).
  2. **Synthetic population forgery** (Serwadda & Phoha): sample dwell and flight from Aalto
     population statistics.
  3. **Targeted mimicry** (Tey et al.): an attacker who sees the victim's mean timings and
     reproduces them with noise. A stronger variant has the victim's full per-feature
     distributions (white-box upper bound).
  4. **Recorded replay:** capture a genuine session's events and replay them with original or
     shifted timestamps, both over the network (should be blocked by A3) and as synthetic
     input events in the browser (should be caught by A8a).
  5. **Profile poisoning:** an attacker who passes one step-up (stolen TOTP) and then drifts
     slowly. Show that the update cap and drift alert limit the effect.
  6. **Unattended-laptop takeover:** real human impostors from the consented set operating
     another user's session.
- Report the detection rate, time-to-detect and FAR under each attack, with honest limits.

### Wave 5: Hardening, evaluation, documentation, demo

**A13 — Observability and deployment** (A1 continues)
- Grafana dashboards: scoring latency p50/p95, stream lag, dropped or rejected batches by
  reason, decisions by outcome, step-up rate, model errors, and the WebSocket client count.
  Alert rules for lag > 5 s and error rate > 1%. A one-command `make up && make seed && make
  demo` that loads demo users, pre-enrolled profiles and policies.

**A14 — QA engineer: end-to-end and replay tests**
- Owns: `tests/e2e/`, `tests/replay/`.
- Load `webapp-testing`. Python Playwright scripts that: (a) log in to Ledgerly, type and move
  like a genuine user using a **recorded genuine fixture**, and assert CONTINUE; (b) run an
  impostor fixture and assert STEP_UP before `add_payee` completes; (c) fail step-up and assert
  termination plus an audit record; (d) scroll only and assert `CANNOT_DETERMINE` on the
  dashboard; (e) capture **every network request from the SDK** during a typing test and assert
  that no typed character appears in any payload (the end-to-end proof of invariant 1);
  (f) take dashboard screenshots for the README.
- Replay tests: feed recorded event streams into the pipeline and assert the decisions are
  deterministic (golden files).

**A15 — Research and evaluation lead**
- Owns: `ml/reports/`, `docs/eval-report.md`.
- Collect every metric in PDF section 13: FAR, FRR, EER, ROC-AUC (per channel and fused),
  time-to-detect, bot and replay detection rate, scoring latency p50/p95, robustness under
  drift (different keyboard, time of day, tiredness, from the consented set where possible),
  robustness under attack (from A16), and user friction (step-ups per genuine user per day,
  simulated over the consented sessions). Include ROC/DET plots, EER-vs-window-length curves,
  and a table comparing the results with the PDF targets (≈9.6% CMU keystroke, under 5% fused
  in about 1 minute, at most 1 genuine step-up per day). **Report misses honestly** and analyse
  why. Add a related-work comparison table based on the PDF's references [1]–[14] and the
  research-gap statement.

**A17 — Documentation and pitch**
- Owns: `README.md`, `docs/demo-script.md`, `docs/architecture.md`, `docs/slides-outline.md`.
- README: what AuthWho is (one paragraph plus the bank-cashier analogy from the PDF),
  quickstart (Windows and Docker Desktop), architecture diagram, screenshots, the privacy
  promise, results table, limitations and future work (touch/mobile per Touchalytics [10],
  federated profiles, in-browser feature extraction).
- Demo script (5 minutes): the problem (an AiTM kit steals a cookie after MFA) → genuine use
  (trust stays HIGH) → scrolling (`CANNOT_DETERMINE`, explained) → laptop handed to an evaluator
  → trust falls and confidence rises → add payee → step-up → failure → termination → incident
  report → bot button → audit verify → "what we collect" page.

### Reviewers (spawned throughout)

- **Task reviewer:** after every implementer task, using the Superpowers reviewer prompts.
- **Security reviewer (A8b):** on security-relevant diffs.
- **Final whole-branch reviewer:** after Wave 5, a fresh agent reviews the whole repository
  against `AuthWho-SPEC.md` and this prompt's invariants, and produces a punch list. Fix it,
  then run `finishing-a-development-branch`.

---

## 7. Phase gates (from PDF section 14; do not start the next wave until the gate passes)

| Gate | Proof required (command output pasted in ledger) |
|---|---|
| P0 Capture | SDK fuzz test plus E2E payload inspection show zero character content; schema-valid batches reach Redis |
| P1 Keystroke | CMU protocol EER table reproduced; best detector EER ≤ ~10% |
| P2 Mouse/interaction | Balabit and SapiMouse per-user EER and AUC table; EER-vs-strokes curve |
| P3 Fusion | Fused EER below every single channel on the same windows; `CANNOT_DETERMINE` triggers on idle/scroll |
| P4 Defences | Bot/replay/synthetic detection rates measured; genuine false-flag rate below 1% |
| P5 Policy | E2E: impostor → STEP_UP → fail → terminate, with an audit record; `/v1/authorize` p95 under 20 ms |
| P6 Dashboard | Every decision has an explanation; live takeover demo runs 5 times in a row without a failure |
| P7 Ops | CI green; `make up` from a clean clone works; Grafana shows live metrics |

---

## 8. Subagent prompt template (fill in for every spawn)

```
You are <ROLE> on the AuthWho project (continuous behavioural biometric authentication).
Repository: <absolute path>. You are working in an isolated git worktree on branch <branch>.

## Context you need (you have NOT seen any prior conversation)
- One-paragraph summary of AuthWho and of where your component sits in the architecture.
- Read these files first: docs/spec/AuthWho-SPEC.md (sections ...), contracts/<files>,
  docs/adr/<relevant>.
- Proposal PDF (for background): C:\Users\05nik\OneDrive\Desktop\aakriti maam project\AuthWho_Project_Proposal-1.pdf, section(s) <n>.

## Non-negotiable invariants
<paste section 2 word for word>

## Your task
<agent card from section 6, expanded into concrete numbered steps>

## Files you own (only edit these)
<paths>. If you need a change elsewhere, do NOT make it. Describe it under "Requested changes"
in your report.

## Skills to load before starting
.claude/skills/test-driven-development/SKILL.md, .claude/skills/verification-before-completion/SKILL.md,
<plus role-specific: frontend-design, webapp-testing, systematic-debugging ...>

## Acceptance criteria
<bullet list; each one testable>

## Verification commands (run them; paste real output in your report)
<e.g. `cd sdk && pnpm test && pnpm lint && pnpm build`, `uv run pytest services/pipeline/fusion -q`>

## Report format (your final message)
1. Summary of what you built (≤10 lines)
2. Files created/changed
3. Verification output (real, untruncated where it matters)
4. Metrics measured (with the script that produced them)
5. Rulings you made + why
6. Requested changes to files you don't own
7. Known limitations / TODOs
Commit your work in your worktree with a clear message. Do not push. Do not merge.
```

---

## 9. Testing and quality bar

- **TDD everywhere:** write a failing test first (`test-driven-development`).
- Coverage: at least 85% on `fusion`, `policy`, `audit`, `detectors`, `features` and the SDK
  core; 100% branch coverage on `policy.decide`.
- **Privacy tests are mandatory and run in CI:** the SDK fuzz test (A2), the E2E network
  capture test (A14), and a DB scan test that dumps all event tables after an E2E run and
  greps for the typed test sentence (it must find zero hits).
- Determinism: fixed seeds; golden-file replay tests for decisions.
- Performance tests: a load script (Locust or a simple asyncio client) simulating 50
  concurrent sessions, reporting ingest and scoring p50/p95.
- Lint and type checks: ruff, mypy (strict on `services/`), ESLint, `tsc --noEmit`.
- Security scans in CI: bandit, pip-audit, npm audit, semgrep. Any High finding fails CI.
- Nothing is "done" without pasted command output (`verification-before-completion`).

---

## 10. Final deliverables checklist

- [ ] `make up && make seed && make demo` works from a clean clone on Windows and Docker Desktop
- [ ] Browser SDK that captures zero character content, proven by 3 independent tests
- [ ] Collector with signed, sequence-numbered, replay-proof ingest
- [ ] Keystroke, mouse and interaction models trained, exported to ONNX and registered in MLflow
- [ ] Bot, replay and synthetic detectors with measured rates
- [ ] Fused trust score with confidence and an explicit `CANNOT_DETERMINE`
- [ ] Policy engine plus Keycloak step-up plus termination, end to end
- [ ] Hash-chained audit log with a verify endpoint
- [ ] Admin dashboard: live sessions, timelines, channel breakdowns, explanations, policy
      editor, incident export, audit verify
- [ ] Ledgerly demo app with enrollment, consent, live demo mode and bot button
- [ ] Prometheus and Grafana dashboards
- [ ] CI green (lint, types, unit, contract, privacy, security scans, docker build)
- [ ] `docs/`: spec, plan, ADRs, threat model, privacy, eval report (honest numbers), demo
      script, ledger, consent form
- [ ] README with screenshots and results table

## 11. Start now

1. `git init`, copy the skills, and read the PDF.
2. Load `brainstorming` → write the spec. Load `writing-plans` → write the plan.
3. Spawn A0 (contracts) and A1 (DevOps scaffold). Review, merge and freeze the contracts.
4. Run Waves 1–5 with parallel subagents (at most 4 coding agents at a time), each followed by
   review, with the phase gates enforced and the ledger kept up to date.
5. At the end, report: what works (with proof), the metrics against the targets, known
   limitations, and the exact commands to run the demo.

=== PROMPT END ===
