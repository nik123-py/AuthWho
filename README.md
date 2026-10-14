# AuthWho

AuthWho is a continuous behavioural biometric authentication engine for desktop web sessions. After a user logs in, it keeps checking that the same person is still operating the session, using typing rhythm, pointer movement and page interaction. When confidence drops it reacts in proportion (monitor, step-up verification with a one-time code, or ending the session), and when there is not enough behaviour to judge it reports "Cannot determine" instead of guessing.

This is a personal student project. The design is in `AuthWho_Project_Proposal.tex`; the build plan is in `PLAN.md` and progress is tracked in `PROGRESS.md`.

Status: the MVP phases P0 to P6 are complete: capture, features, models, continuous trust, policy and step-up, the admin dashboard with live demo mode, and the evaluation report (`docs/evaluation_report.md`). The consented volunteer dataset is not collected yet; a clearly labelled synthetic cohort of 25 people stands in for it. To deploy, see `docs/deployment.md`.

## What is and is not collected

Collected, only after consent, and only for channels the user has not opted out of:

- Key-down and key-up times with a coarse key category (letter, digit, space, backspace, modifier, navigation, other).
- Pointer coordinates and times, clicks, wheel and scroll movement.
- Focus changes between form fields (by position on the page, not by name), page changes, whether copy, cut or paste happened, and whether the tab is visible.
- The pointing device the user declared (mouse or touchpad).

Never collected:

- Which characters or keys were typed, the contents of any field, or clipboard contents.
- Any keystrokes inside password fields.
- Names, emails or passwords. AuthWho sees only a pseudonymous user ID.

Retention:

| Data | Where | How long |
|---|---|---|
| Raw event batches | Redis Streams, in memory only | At most 24 hours |
| Window feature vectors | PostgreSQL, encrypted | 30 days, rolling |
| Profile templates | PostgreSQL, encrypted | Until re-enrollment or account deletion |
| Decision records | PostgreSQL | 90 days |
| Volunteer research data (research consent only) | Encrypted local files, pseudonymous IDs | Until the project ends |

The strongest action AuthWho can take is to ask for a one-time code again or end the session. It never disables an account.

## Requirements (Windows)

- Python 3.11 or later (developed on 3.14)
- Node.js 20 or later (developed on 24)
- Git
- Docker Desktop, running

## Setup

From the repository root, in Git Bash:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
npm install
cp .env.example .env        # then replace the dummy values
docker compose up -d        # PostgreSQL and Redis
```

In PowerShell, use `.venv\Scripts\python` and `Copy-Item .env.example .env`.

## Running the demo and inspecting a capture

Open four terminals in the repository root (Git Bash shown; in PowerShell use `.venv\Scripts\python`).

```bash
# 1. Database and Redis, then the schema
docker compose up -d --wait
.venv/Scripts/python -m server.db.migrate --env-file .env

# 2. AuthWho API (collector) on port 8000
.venv/Scripts/python -m uvicorn server.api.app:app --host 127.0.0.1 --port 8000 --env-file .env

# 3. Demo app backend on port 8100
.venv/Scripts/python -m uvicorn demo_app.backend.app:app --host 127.0.0.1 --port 8100 --env-file .env

# 4. Demo app frontend on port 5173
npm run dev -w demo_app/frontend

# 5. Worker: features, enrollment, scoring, trust and policy
.venv/Scripts/python -m server.worker --env-file .env
```

After enrollment (20 windows per channel by default; set `AUTHWHO_ENROLL_WINDOWS=5` for a quick demo), every window is scored and the session's trust is updated. When typing or mouse movement no longer matches, a high-risk action (adding a payee or exporting a report) asks "Confirm it is you": the authenticator code if one is set up in Settings, otherwise the password. Three wrong answers end the session.

Then open http://localhost:5173, register, read and accept the consent form, and type, click and scroll on the Write and Form pages for a minute. To see exactly what was captured, find the session ID and dump it:

```bash
docker compose exec postgres psql -U authwho -d authwho -c "select session_id, created_at from sessions order by created_at desc limit 3;"
.venv/Scripts/python -m server.collector.dump <session_id> --env-file .env
.venv/Scripts/python -m server.collector.dump <session_id> --json --env-file .env
```

Every event shows only its type, time, category or coordinates. Raw events disappear from Redis after 24 hours. Users who also ticked research consent get an encrypted copy under `data/volunteer/` while `python -m server.research --env-file .env` is running.

## Admin dashboard

```bash
npm run dev -w dashboard        # http://localhost:5174, sign in with AUTHWHO_ADMIN_TOKEN
```

Sessions with live trust, each session's trust timeline with decisions and their explanations, a channel breakdown, an incident report export, the policy editor, and a live demo page that follows whichever session changed most recently.

## Synthetic cohort

```bash
.venv/Scripts/python -m ml.synthetic --users 25 --out data/synthetic      # 25 people, 6 sessions each
.venv/Scripts/python -m experiments.synthetic_evaluation                  # every Section 13 metric
.venv/Scripts/python -m ml.load_synthetic --env-file .env                 # replay them into a running stack
```

The generator's parameters are fitted to the public Aalto and SapiMouse data (`experiments/results/synthetic_calibration.md`). Results on it test the system end to end; they are not measurements of real people.

## Production

`docker-compose.prod.yml` runs the whole system behind nginx with one command, and every service refuses to start with placeholder secrets. See `docs/deployment.md`.

## Running the tests

```bash
.venv/Scripts/python -m pytest              # all Python tests
.venv/Scripts/python -m pytest -m "not integration"   # without Docker
npm test                                    # Vitest in every workspace
```

Integration tests need `docker compose up -d` first. End-to-end tests run in a real browser; see `tests/e2e/README.md`.

## Repository layout

| Path | Contents |
|---|---|
| `sdk/` | TypeScript browser SDK |
| `server/` | Collector, feature extraction, worker, policy engine, admin API |
| `ml/`, `experiments/` | Models, evaluation and experiment scripts |
| `demo_app/` | Demo web application (backend and frontend) |
| `dashboard/` | Admin dashboard |
| `tests/e2e/` | Playwright end-to-end tests |
| `docs/` | Interfaces, dependencies and reports |
