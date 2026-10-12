# Approved dependencies

Agents may use only what is listed here. Anything else must be requested through the orchestrator, who asks the project owner. All items are free and open source. Python packages install into the project virtual environment `.venv`; JavaScript packages install into the npm workspaces. Nothing is installed system-wide.

Status: **approved by the owner on 2026-10-09.**

## Runtime and tools already on the laptop

| Tool | Version found | Notes |
|---|---|---|
| Python | 3.14.6 | Proposal needs 3.11 or later. Docker images use `python:3.14-slim` to match |
| Node.js / npm | 24.19.0 / 11.17.0 | Proposal needs Node 20 or later |
| Git | installed | |
| Docker Desktop | 28.5.1 | Must be running for integration and end-to-end tests |

## Python

| Package | In proposal stack | Purpose |
|---|---|---|
| fastapi | yes | Collector, admin API, demo backend |
| uvicorn[standard] | yes (FastAPI server) | ASGI server |
| pydantic | yes (part of FastAPI) | Schema validation |
| redis | yes (Redis client) | Redis Streams, hot state, pub/sub |
| psycopg[binary] (v3) | yes (PostgreSQL client) | PostgreSQL access. Migrations are plain SQL files run by a small runner, so no ORM or Alembic |
| numpy, pandas, scikit-learn | yes | Features, models, evaluation (scikit-learn brings scipy) |
| pyotp | yes | TOTP step-up |
| cryptography | no, needed for "encrypted at rest" in Section 9 | AES-256-GCM for window vectors, templates, TOTP secrets and research files |
| httpx | no, needed by FastAPI's TestClient | Test client, server-to-server calls from the demo backend |
| pytest | yes | Unit and integration tests |
| playwright, pytest-playwright | no, required by the build prompt | End-to-end tests (Playwright for Python). Browser binaries download into the user cache with `playwright install chromium firefox` |

Password hashing in the demo app uses the standard library (`hashlib.scrypt`), so no extra package is needed.

## JavaScript (npm workspaces: `sdk`, `dashboard`, `demo_app/frontend`)

| Package | In proposal stack | Purpose |
|---|---|---|
| typescript | yes | All frontend code |
| vite | no, required by the build prompt | Dev server and builds; library mode for the SDK |
| vitest | no, required by the build prompt | Unit tests |
| jsdom | no, needed by Vitest for DOM tests | Simulated browser for SDK and component tests |
| react, react-dom | yes | Dashboard and demo frontend |
| @vitejs/plugin-react | no, needed for React with Vite | Build plugin |
| tailwindcss, @tailwindcss/vite | no, required by the build prompt | Styling |
| chart.js | yes | Trust timeline (used directly, no wrapper package) |
| react-router-dom | no | Page routing in the dashboard and demo app |
| @testing-library/react, @testing-library/user-event, @testing-library/jest-dom | no | Component tests |

## Docker images

| Image | Purpose |
|---|---|
| postgres:16-alpine | Database |
| redis:7-alpine | Event stream and hot state |
| python:3.14-slim | API, worker and demo backend containers (added in P5) |
| node:24-alpine | Frontend build containers (added in P5) |

## Datasets (downloaded only from official sources into `data/`, never committed)

| Dataset | Official source |
|---|---|
| CMU Keystroke Dynamics benchmark | https://www.cs.cmu.edu/~keystroke/ |
| Aalto 136M keystrokes | https://userinterfaces.aalto.fi/136Mkeystrokes/ (a documented subset is used on the laptop) |
| Balabit Mouse Dynamics Challenge | https://github.com/balabit/Mouse-Dynamics-Challenge |
| SapiMouse | Official page linked from Antal, Fejer and Buza (2021) |
