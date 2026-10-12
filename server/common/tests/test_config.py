import base64

import pytest

from server.common.config import ConfigError, load_env_file, load_settings


def _b64(n=32, fill=b"k"):
    return base64.b64encode(fill * n).decode()


FULL = {
    "AUTHWHO_DATABASE_URL": "postgresql://u:p@localhost:5432/db",
    "AUTHWHO_REDIS_URL": "redis://localhost:6379/0",
    "AUTHWHO_DATA_KEY": _b64(),
    "AUTHWHO_APP_API_KEY": "app-key",
    "AUTHWHO_ADMIN_TOKEN": "admin",
    "AUTHWHO_CORS_ORIGINS": "http://localhost:5173, http://localhost:5174",
    "RESEARCH_EXPORT_KEY": _b64(fill=b"r"),
}


def test_reads_all_values_from_environment_mapping():
    s = load_settings(FULL)
    assert s.database_url == FULL["AUTHWHO_DATABASE_URL"]
    assert s.redis_url == FULL["AUTHWHO_REDIS_URL"]
    assert s.data_key == b"k" * 32
    assert s.research_export_key == b"r" * 32
    assert s.app_api_key == "app-key"
    assert s.admin_token == "admin"
    assert s.cors_origins == ("http://localhost:5173", "http://localhost:5174")


def test_missing_optional_values_are_none_and_require_raises_with_name():
    s = load_settings({})
    assert s.database_url is None
    assert s.cors_origins == ()
    with pytest.raises(ConfigError, match="AUTHWHO_APP_API_KEY"):
        s.require("app_api_key")


def test_bad_key_length_is_rejected_without_echoing_value():
    env = dict(FULL, AUTHWHO_DATA_KEY=_b64(n=16, fill=b"z"))
    with pytest.raises(ConfigError) as info:
        load_settings(env)
    assert "AUTHWHO_DATA_KEY" in str(info.value)
    assert env["AUTHWHO_DATA_KEY"] not in str(info.value)


def test_load_env_file_parses_simple_lines_and_does_not_override(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n\nA=1\nB = two words \nC='quoted'\nD=\"dq\"\nE=x=y\n",
        encoding="utf-8",
    )
    target = {"A": "keep"}
    load_env_file(path, target)
    assert target == {"A": "keep", "B": "two words", "C": "quoted", "D": "dq", "E": "x=y"}
