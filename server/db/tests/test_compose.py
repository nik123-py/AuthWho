"""docker-compose.yml gives each container only the environment it needs."""

import json
import shutil
import subprocess

import pytest

from server.common.testing import REPO_ROOT

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker is not installed"),
]


@pytest.fixture(scope="module")
def compose():
    # .env.example holds dummy values only, so this never reads real secrets.
    out = subprocess.run(
        ["docker", "compose", "--env-file", ".env.example", "config", "--format", "json"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=60,
    )
    return json.loads(out.stdout)["services"]


def test_postgres_gets_only_its_three_variables(compose):
    env = compose["postgres"].get("environment") or {}
    assert set(env) == {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}
    assert env["POSTGRES_USER"] == "authwho"  # substituted from the env file


def test_redis_gets_no_environment_and_no_persistence(compose):
    assert not compose["redis"].get("environment")
    assert compose["redis"]["command"] == ["redis-server", "--save", "", "--appendonly", "no"]


def test_no_service_loads_a_whole_env_file(compose):
    for name, service in compose.items():
        assert not service.get("env_file"), name
