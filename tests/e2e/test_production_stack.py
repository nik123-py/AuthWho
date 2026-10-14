"""Smoke test for a deployed production stack (docker-compose.prod.yml).

Runs only when pointed at a deployment:
    AUTHWHO_PROD_URL=http://localhost:8088 AUTHWHO_PROD_ADMIN_TOKEN=... \\
        .venv/Scripts/python -m pytest tests/e2e/test_production_stack.py -m prod
"""

from __future__ import annotations

import os
import random

import httpx
import pytest

pytestmark = pytest.mark.prod

BASE = os.environ.get("AUTHWHO_PROD_URL", "").rstrip("/")
TOKEN = os.environ.get("AUTHWHO_PROD_ADMIN_TOKEN", "")
PASSWORD = "correct horse 1"

if not BASE:
    pytest.skip("AUTHWHO_PROD_URL is not set", allow_module_level=True)


def test_security_headers_and_public_surface():
    r = httpx.get(BASE + "/")
    assert r.status_code == 200 and "<div id=\"root\">" in r.text
    for header in ("content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy"):
        assert header in r.headers
    assert "server" not in r.headers or "nginx/" not in r.headers["server"]
    assert httpx.get(BASE + "/healthz").json() == {"status": "ok"}
    assert httpx.put(BASE + "/v1/users/00000000-0000-4000-8000-000000000000", json={}).status_code == 404
    assert httpx.post(BASE + "/v1/sessions", json={}).status_code == 404
    assert httpx.get(BASE + "/v1/admin/sessions").status_code == 401
    assert httpx.get(BASE + "/v1/admin/sessions", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


def test_user_flow_and_dashboard(page, browser):
    user = f"prod_{random.randrange(16**8):08x}"
    page.goto(BASE + "/register")
    page.get_by_label("Username").fill(user)
    page.get_by_label("Password", exact=True).fill(PASSWORD)
    page.get_by_label("Confirm password").fill(PASSWORD)
    page.get_by_role("button", name="Create account").click()
    page.get_by_role("heading", name="Consent and enrollment").wait_for()
    page.get_by_label("Mouse", exact=True).check()
    page.get_by_label("I agree to the collection described on this page").check()
    page.get_by_role("button", name="Give consent").click()
    page.get_by_role("link", name="Write", exact=True).click()
    page.get_by_label("Your note").click()
    rng = random.Random(1)
    with page.expect_response(lambda r: r.url.endswith("/v1/batches")) as batch:
        for ch in "hello from production " * 3:
            key = "Space" if ch == " " else ch
            page.keyboard.down(key)
            page.wait_for_timeout(70 + rng.random() * 40)
            page.keyboard.up(key)
            page.wait_for_timeout(90 + rng.random() * 60)
    assert batch.value.status == 202

    admin = browser.new_page()
    admin.goto(BASE + "/admin/")
    admin.get_by_label("Admin token").fill(TOKEN)
    admin.get_by_role("button", name="Sign in").click()
    admin.get_by_role("table", name="Sessions").wait_for()
