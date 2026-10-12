"""Configuration read from environment variables (docs/interfaces.md section 3).

Values are read from ``os.environ``. For local command-line tools,
``load_env_file`` merges a ``.env`` file into the environment without
overriding variables that are already set. The API server is started with
``uvicorn server.api.app:app --env-file .env``, which uses uvicorn's own loader.
Error messages name the variable but never include its value.
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, fields
from pathlib import Path

from server.common.crypto import KEY_BYTES


class ConfigError(Exception):
    """Missing or invalid configuration."""


_ENV_NAMES = {
    "database_url": "AUTHWHO_DATABASE_URL",
    "redis_url": "AUTHWHO_REDIS_URL",
    "data_key": "AUTHWHO_DATA_KEY",
    "app_api_key": "AUTHWHO_APP_API_KEY",
    "admin_token": "AUTHWHO_ADMIN_TOKEN",
    "cors_origins": "AUTHWHO_CORS_ORIGINS",
    "research_export_key": "RESEARCH_EXPORT_KEY",
}


@dataclass(frozen=True)
class Settings:
    database_url: str | None = None
    redis_url: str | None = None
    data_key: bytes | None = None
    app_api_key: str | None = None
    admin_token: str | None = None
    cors_origins: tuple[str, ...] = ()
    research_export_key: bytes | None = None

    def require(self, name: str):
        value = getattr(self, name)
        if value is None or value == () or value == "":
            raise ConfigError(f"{_ENV_NAMES[name]} is not set")
        return value


def _decode_key(env_name: str, raw: str) -> bytes:
    try:
        key = base64.b64decode(raw.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ConfigError(f"{env_name} is not valid base64") from exc
    if len(key) != KEY_BYTES:
        raise ConfigError(f"{env_name} must decode to {KEY_BYTES} bytes")
    return key


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    values = {}
    for field in fields(Settings):
        env_name = _ENV_NAMES[field.name]
        raw = env.get(env_name)
        if raw is None or raw.strip() == "":
            continue
        if field.name.endswith("_key") and field.name != "app_api_key":
            values[field.name] = _decode_key(env_name, raw)
        elif field.name == "cors_origins":
            values[field.name] = tuple(o.strip() for o in raw.split(",") if o.strip())
        else:
            values[field.name] = raw.strip()
    return Settings(**values)


def load_env_file(path: str | Path, target: MutableMapping[str, str] | None = None) -> None:
    """Merge simple KEY=VALUE lines into ``target`` (default ``os.environ``).

    Existing keys are kept. Blank lines and lines starting with ``#`` are
    ignored; matching single or double quotes around a value are removed.
    """
    env = os.environ if target is None else target
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        env.setdefault(name, value)
