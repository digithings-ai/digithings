"""JWT consumers must receive the revocation blocklist, not only digikey.

Compose used to set DIGIKEY_JWKS_URL on digigraph, digiquant, digisearch,
digivault, and digisearch-mcp without DIGIKEY_BLOCKLIST_REDIS_URL. With the
blocklist required by default, those processes 503 every authenticated request.
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
REDIS_DEFAULT = "redis://digikey-blocklist-redis:6379/0"


def _env_map(env: object) -> dict[str, str]:
    if isinstance(env, dict):
        return {str(k): "" if v is None else str(v) for k, v in env.items()}
    if isinstance(env, list):
        mapped: dict[str, str] = {}
        for item in env:
            text = str(item)
            key, _, value = text.partition("=")
            mapped[key] = value
        return mapped
    return {}


@pytest.mark.parametrize("compose_path", COMPOSE_FILES, ids=lambda p: p.name)
def test_jwt_consumers_fail_closed_on_the_blocklist(compose_path: Path) -> None:
    doc = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for name, service in doc["services"].items():
        env = _env_map(service.get("environment"))
        if "DIGIKEY_JWKS_URL" not in env:
            continue
        redis = env.get("DIGIKEY_BLOCKLIST_REDIS_URL", "")
        require = env.get("DIGIKEY_REQUIRE_BLOCKLIST", "")
        if REDIS_DEFAULT not in redis or not require.endswith(":-1}"):
            offenders.append(name)
    assert offenders == []
