"""Production safety checks and secret generation.

With ``AUTHWHO_ENV=production`` every service calls ``require_production_ready``
at startup and refuses to start if a secret is missing, a known dummy value, too
short, or a key of the wrong length, or if login cookies would not be Secure.
Messages name the variable but never echo its value.

Generate a fresh production environment file with:
    .venv/Scripts/python -m server.common.production --domain authwho.example.org > .env.production
"""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import secrets
import sys
from collections.abc import Mapping

KEYS_32 = ("AUTHWHO_DATA_KEY", "RESEARCH_EXPORT_KEY", "DEMO_TOTP_KEY")
TOKENS = ("AUTHWHO_APP_API_KEY", "AUTHWHO_ADMIN_TOKEN", "DEMO_SECRET_KEY", "POSTGRES_PASSWORD")
MIN_TOKEN_LENGTH = 32
_DUMMY_MARKERS = (b"dummy", b"change-me", b"changeme", b"example")


def _looks_dummy(raw: bytes) -> bool:
    low = raw.lower()
    return any(m in low for m in _DUMMY_MARKERS)


def check_production(env: Mapping[str, str]) -> list[str]:
    if env.get("AUTHWHO_ENV", "development").lower() != "production":
        return []
    problems = []
    for name in KEYS_32:
        value = env.get(name, "")
        if not value:
            problems.append(f"{name} is not set")
            continue
        try:
            key = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            problems.append(f"{name} is not valid base64")
            continue
        if len(key) != 32:
            problems.append(f"{name} must decode to 32 bytes")
        elif _looks_dummy(key):
            problems.append(f"{name} is a placeholder value; generate a random key")
    for name in TOKENS:
        value = env.get(name, "")
        if len(value) < MIN_TOKEN_LENGTH:
            problems.append(f"{name} must be at least {MIN_TOKEN_LENGTH} characters")
        elif _looks_dummy(value.encode()):
            problems.append(f"{name} is a placeholder value; generate a random secret")
    if env.get("DEMO_SECURE_COOKIES", "").lower() not in ("1", "true", "yes"):
        problems.append("DEMO_SECURE_COOKIES must be true in production (serve over HTTPS)")
    return problems


def require_production_ready(env: Mapping[str, str] | None = None) -> None:
    problems = check_production(os.environ if env is None else env)
    if problems:
        print("AuthWho refuses to start in production:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        raise SystemExit(2)


def generate_env(domain: str) -> str:
    def key() -> str:
        return base64.b64encode(secrets.token_bytes(32)).decode()

    def token() -> str:
        return secrets.token_urlsafe(36)

    pg_password = secrets.token_hex(24)
    origin = f"https://{domain}"
    lines = [
        "# AuthWho production environment. Generated; keep it secret and out of version control.",
        "AUTHWHO_ENV=production",
        "POSTGRES_USER=authwho",
        f"POSTGRES_PASSWORD={pg_password}",
        "POSTGRES_DB=authwho",
        f"AUTHWHO_DATABASE_URL=postgresql://authwho:{pg_password}@postgres:5432/authwho",
        "AUTHWHO_REDIS_URL=redis://redis:6379/0",
        f"AUTHWHO_DATA_KEY={key()}",
        f"RESEARCH_EXPORT_KEY={key()}",
        f"AUTHWHO_APP_API_KEY={token()}",
        f"AUTHWHO_ADMIN_TOKEN={token()}",
        f"AUTHWHO_CORS_ORIGINS={origin}",
        "AUTHWHO_COLLECTOR_URL=http://api:8000",
        "AUTHWHO_ENROLL_WINDOWS=20",
        f"DEMO_PUBLIC_COLLECTOR_URL={origin}",
        "DEMO_DB_PATH=/data/demo/demo.sqlite",
        f"DEMO_SECRET_KEY={token()}",
        f"DEMO_TOTP_KEY={key()}",
        "DEMO_SECURE_COOKIES=true",
        "DEMO_SESSION_HOURS=12",
        "DEMO_WITHDRAWAL_RETRY_SECONDS=300",
        f"PUBLIC_DOMAIN={domain}",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Print a production .env with fresh random secrets.")
    ap.add_argument("--domain", required=True, help="public host name, for example authwho.example.org")
    print(generate_env(ap.parse_args().domain), end="")


if __name__ == "__main__":
    main()
