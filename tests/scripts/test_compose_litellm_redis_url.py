"""LiteLLM must not receive an empty REDIS_URL from compose (#3469).

``REDIS_URL=${REDIS_URL:-}`` interpolates to ``""`` when the var is unset
(``.env.example`` leaves it commented). LiteLLM ``main-stable`` then treats Redis
as configured and exits 3:

``ValueError: Redis URL must specify one of the following schemes``.

Smoke: stack copies ``.env.example`` → ``.env``, so that empty injection is
what killed the nightly compose probe.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = (
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "infra" / "digichat-release" / "compose.profile-a.yml",
)
SMOKE_STACK = REPO_ROOT / ".github" / "workflows" / "smoke-stack.yml"
EMPTY_REDIS_DEFAULT = "${REDIS_URL:-}"


def _litellm_env_values(compose_path: Path) -> list[str]:
    doc = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    env = doc["services"]["litellm"].get("environment")
    if env is None:
        return []
    if isinstance(env, dict):
        return [f"{k}={v}" for k, v in env.items()]
    if isinstance(env, list):
        return [str(item) for item in env]
    raise TypeError(f"{compose_path}: unexpected litellm.environment type {type(env)}")


@pytest.mark.parametrize("compose_path", COMPOSE_FILES, ids=lambda p: p.name)
def test_litellm_does_not_inject_empty_redis_url(compose_path: Path) -> None:
    values = _litellm_env_values(compose_path)
    offenders = [v for v in values if EMPTY_REDIS_DEFAULT in v or v in ("REDIS_URL=", "REDIS_URL")]
    assert offenders == [], (
        f"{compose_path}: LiteLLM environment injects empty REDIS_URL {offenders}; "
        "omit the var so env_file can pass a real URL when the cache profile is on"
    )
    assert not any(v.startswith("REDIS_URL=") and v.split("=", 1)[1] == "" for v in values)


def test_smoke_stack_dumps_litellm_logs_on_compose_failure() -> None:
    doc = yaml.safe_load(SMOKE_STACK.read_text(encoding="utf-8"))
    steps = doc["jobs"]["healthz"]["steps"]
    dump = next(
        (s for s in steps if s.get("name") == "Dump compose logs on failure"),
        None,
    )
    assert dump is not None, "smoke-stack.yml must dump LiteLLM logs when compose up fails"
    assert dump.get("if") == "failure()"
    run = dump["run"]
    assert "docker compose logs" in run
    assert "litellm" in run
