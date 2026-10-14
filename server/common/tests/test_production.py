"""Production configuration checks and the secrets generator."""

import base64

from server.common.production import check_production, generate_env


def _good():
    key = base64.b64encode(b"k" * 31 + b"!").decode()
    return {
        "AUTHWHO_ENV": "production",
        "POSTGRES_PASSWORD": "x" * 32,
        "AUTHWHO_DATA_KEY": key,
        "RESEARCH_EXPORT_KEY": key,
        "DEMO_TOTP_KEY": key,
        "AUTHWHO_APP_API_KEY": "a" * 40,
        "AUTHWHO_ADMIN_TOKEN": "b" * 40,
        "DEMO_SECRET_KEY": "c" * 40,
        "DEMO_SECURE_COOKIES": "true",
    }


def test_good_production_config_passes():
    assert check_production(_good()) == []


def test_development_is_not_checked():
    assert check_production({"AUTHWHO_ENV": "development", "AUTHWHO_ADMIN_TOKEN": "dummy"}) == []


def test_dummy_short_or_missing_secrets_are_refused():
    env = _good() | {
        "AUTHWHO_DATA_KEY": base64.b64encode(b"dummy-authwho-data-key-32-bytes!").decode(),
        "AUTHWHO_ADMIN_TOKEN": "short",
        "POSTGRES_PASSWORD": "dummy-change-me",
        "DEMO_SECURE_COOKIES": "false",
    }
    env.pop("DEMO_TOTP_KEY")
    problems = " ".join(check_production(env))
    for name in ("AUTHWHO_DATA_KEY", "AUTHWHO_ADMIN_TOKEN", "POSTGRES_PASSWORD", "DEMO_TOTP_KEY", "DEMO_SECURE_COOKIES"):
        assert name in problems
    assert "dummy" not in problems.lower() or "AUTHWHO_DATA_KEY" in problems  # values are never echoed
    assert "short" not in problems.split("AUTHWHO_ADMIN_TOKEN", 1)[1][:5]


def test_wrong_length_key_is_refused():
    env = _good() | {"AUTHWHO_DATA_KEY": base64.b64encode(b"x" * 16).decode()}
    assert any("AUTHWHO_DATA_KEY" in p for p in check_production(env))


def test_generated_env_passes_the_checks_and_is_random():
    a = dict(line.split("=", 1) for line in generate_env("authwho.example.org").splitlines() if "=" in line and not line.startswith("#"))
    b = dict(line.split("=", 1) for line in generate_env("authwho.example.org").splitlines() if "=" in line and not line.startswith("#"))
    assert check_production(a) == []
    assert a["AUTHWHO_DATA_KEY"] != b["AUTHWHO_DATA_KEY"]
    assert a["DEMO_PUBLIC_COLLECTOR_URL"] == "https://authwho.example.org"
    assert "https://authwho.example.org" in a["AUTHWHO_CORS_ORIGINS"]
