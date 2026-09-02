"""OmniRoute compose profile must not break default ``docker compose config`` (#3413)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"


def test_omniroute_password_is_not_required_at_compose_config() -> None:
    """Compose interpolates inactive profiles during ``docker compose config -q``.

    ``${OMNIROUTE_AUTH_PASSWORD:?...}`` made the default (no-profile) validate job
    fail without that secret. Empty-default interpolation is required; the
    password is enforced when the profile actually starts.
    """
    text = COMPOSE.read_text(encoding="utf-8")
    assert "OMNIROUTE_AUTH_PASSWORD:?" not in text
    assert "${OMNIROUTE_AUTH_PASSWORD:-}" in text


def test_omniroute_profile_is_opt_in_and_guards_password_at_start() -> None:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = data["services"]
    omni = services["omniroute"]
    guard = services["omniroute-auth-guard"]
    assert omni.get("profiles") == ["omniroute"]
    assert guard.get("profiles") == ["omniroute"]
    depends = omni.get("depends_on") or {}
    assert "omniroute-auth-guard" in depends
    env = omni.get("environment") or []
    assert any(
        isinstance(item, str) and item.startswith("INITIAL_PASSWORD=${OMNIROUTE_AUTH_PASSWORD:-}")
        for item in env
    )
