"""End-to-end fixtures: the whole AuthWho stack on test ports, driven by a real browser.

The stack uses the Docker Compose PostgreSQL and Redis (``docker compose up -d``
first) and the local ``.env``. It starts, on ports that do not clash with a
development setup: the AuthWho API (18000), the worker (enrollment after 5
windows), the demo backend (18100, its own temporary SQLite file) and the demo
frontend dev server (15173) and the admin dashboard (15174). Every process started here is stopped here, by
its own handle; nothing else is touched. All behaviour is scripted.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psycopg
import pytest
import redis

from server.common.config import load_env_file

ROOT = Path(__file__).resolve().parents[2]
API, DEMO, WEB, DASH = 18000, 18100, 15173, 15174
PASSWORD = "correct horse 1"


def _env(tmp: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if (ROOT / ".env").exists():  # CI passes the same variables through the environment instead
        load_env_file(ROOT / ".env", env)
    env.update(os.environ)
    env.update({
        "AUTHWHO_ENROLL_WINDOWS": "5",
        "AUTHWHO_COLLECTOR_URL": f"http://127.0.0.1:{API}",
        "AUTHWHO_CORS_ORIGINS": f"http://localhost:{WEB},http://127.0.0.1:{WEB}",
        "DEMO_DB_PATH": str(tmp / "demo.sqlite"),
        "DEMO_BACKEND_URL": f"http://127.0.0.1:{DEMO}",
        "AUTHWHO_API_URL": f"http://127.0.0.1:{API}",
        "PYTHONUNBUFFERED": "1",
    })
    return env


def _wait(url: str, seconds: float = 60.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2.0).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"{url} did not start")


@pytest.fixture(scope="session")
def stack(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    env = _env(tmp)
    py = sys.executable
    subprocess.run([py, "-m", "server.db.migrate"], cwd=ROOT, env=env, check=True, capture_output=True)
    npx = shutil.which("npx") or "npx"
    commands = {
        "api": [py, "-m", "uvicorn", "server.api.app:app", "--host", "127.0.0.1", "--port", str(API)],
        "worker": [py, "-m", "server.worker"],
        "demo": [py, "-m", "uvicorn", "demo_app.backend.app:app", "--host", "127.0.0.1", "--port", str(DEMO)],
        "web": [npx, "vite", "--port", str(WEB), "--strictPort", "--host", "127.0.0.1"],
        "dash": [npx, "vite", "--port", str(DASH), "--strictPort", "--host", "127.0.0.1"],
    }
    procs = {}
    try:
        for name, cmd in commands.items():
            cwd = {"web": ROOT / "demo_app" / "frontend", "dash": ROOT / "dashboard"}.get(name, ROOT)
            log = open(tmp / f"{name}.log", "w", encoding="utf-8")
            procs[name] = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
        _wait(f"http://127.0.0.1:{API}/healthz")
        _wait(f"http://127.0.0.1:{DEMO}/api/registry")
        _wait(f"http://127.0.0.1:{WEB}/")
        _wait(f"http://127.0.0.1:{DASH}/")
        yield {
            "web": f"http://127.0.0.1:{WEB}",
            "dash": f"http://127.0.0.1:{DASH}",
            "admin_token": env["AUTHWHO_ADMIN_TOKEN"],
            "api": f"http://127.0.0.1:{API}",
            "demo": f"http://127.0.0.1:{DEMO}",
            "db": env["AUTHWHO_DATABASE_URL"],
            "redis": env["AUTHWHO_REDIS_URL"],
            "app_key": env["AUTHWHO_APP_API_KEY"],
            "logs": tmp,
            "demo_db": tmp / "demo.sqlite",
        }
    finally:
        for proc in procs.values():
            if proc.poll() is None:
                if sys.platform == "win32":  # stop the process tree we started (vite starts node children)
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
                else:
                    proc.terminate()
                proc.wait(timeout=20)


@pytest.fixture
def db(stack):
    with psycopg.connect(stack["db"], autocommit=True) as conn:
        yield conn


@pytest.fixture
def rds(stack):
    client = redis.Redis.from_url(stack["redis"], decode_responses=True)
    yield client
    client.close()


def unique_user() -> str:
    return f"e2e_{random.randrange(16**8):08x}"


def register_and_consent(page, base: str, username: str) -> None:
    page.goto(f"{base}/register")
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    page.get_by_label("Confirm password").fill(PASSWORD)
    page.get_by_role("button", name="Create account").click()
    page.get_by_role("heading", name="Consent and enrollment").wait_for()
    page.get_by_label("Mouse", exact=True).check()
    page.get_by_label("I agree to the collection described on this page").check()
    page.get_by_role("button", name="Give consent").click()
    page.get_by_role("link", name="Write", exact=True).wait_for()


def human_type(page, chars: int, hold_ms: float, gap_ms: float, seed: int, jitter: float = 0.35) -> None:
    """Type with per-key random holds and gaps, as a person would (a fixed rhythm is flagged as a bot)."""
    rng = random.Random(seed)
    text = "the quick brown fox jumps over the lazy dog while the band plays on "
    for i in range(chars):
        ch = text[i % len(text)]
        key = "Space" if ch == " " else ch
        page.keyboard.down(key)
        page.wait_for_timeout(hold_ms * (1 + jitter * (rng.random() - 0.5)))
        page.keyboard.up(key)
        page.wait_for_timeout(gap_ms * (1 + jitter * (rng.random() - 0.5)))


def latest_session(stack, db, username: str) -> tuple[str, str]:
    """(AuthWho user id, latest AuthWho session id) for a demo username."""
    import sqlite3

    with sqlite3.connect(stack["demo_db"]) as conn:
        user_id = conn.execute("SELECT authwho_user_id FROM users WHERE username = ?", (username,)).fetchone()[0]
    row = db.execute("SELECT session_id FROM sessions WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
                     (user_id,)).fetchone()
    return user_id, str(row[0]) if row else ""


def wait_for(predicate, seconds: float = 60.0, every: float = 1.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(every)
    raise AssertionError("condition not met in time")
