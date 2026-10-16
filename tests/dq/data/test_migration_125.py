"""Unit tests for migration 125 — drop retired grounding purposes (#3859).

Tool-only grounding retires the web_grounding / x_grounding synthesis
purposes: grounding arrives via the first-party web_search tool (purposes
web_search / x_search). Migration 125 rewrites the inline purpose CHECK
that migration 067 created with the two retired values removed. 067 stays
immutable, so this file pins both sides: 067 still lists the retired
purposes, 125 drops and re-adds the CHECK without them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
M125 = MIGRATIONS_DIR / "125_drop_grounding_purposes.sql"
M121 = MIGRATIONS_DIR / "121_checkpoint_blobs_nullable.sql"
M067 = MIGRATIONS_DIR / "067_olympus_provider_telemetry.sql"

SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)

RETIRED_PURPOSES = ("web_grounding", "x_grounding")
KEPT_PURPOSES = (
    "initial_generation",
    "chat_completion",
    "structured_completion",
    "structured_repair",
    "tool_selection",
    "tool_follow_up",
    "tool_loop",
    "web_search",
    "x_search",
    "embedding",
)


@pytest.fixture(scope="module")
def raw() -> str:
    assert M125.is_file(), f"migration missing: {M125}"
    return M125.read_text(encoding="utf-8")


def test_migration_125_is_only_125_file() -> None:
    assert sorted(MIGRATIONS_DIR.glob("125_*.sql")) == [M125]


def test_header_convention_matches_119_to_121(raw: str) -> None:
    """First-six-line shape must match 121 exactly, modulo the filename."""
    prior = M121.read_text(encoding="utf-8").splitlines()
    lines = raw.splitlines()
    assert lines[0] == f"-- {M125.name}"
    assert lines[1:6] == prior[1:6]


def test_single_transaction_compatible(raw: str) -> None:
    """Unwrapped: db-migrate.yml applies file + ledger INSERT atomically."""
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_retires_grounding_purposes(raw: str) -> None:
    """125 drops and re-adds the purpose CHECK without the retired values."""
    lowered = raw.lower()
    assert "drop constraint olympus_provider_calls_purpose_check" in lowered
    assert "add constraint olympus_provider_calls_purpose_check check" in lowered
    for purpose in RETIRED_PURPOSES:
        assert f"'{purpose}'" not in lowered
    for purpose in KEPT_PURPOSES:
        assert f"'{purpose}'" in lowered


def test_067_still_lists_retired_purposes() -> None:
    """067 is immutable: it still creates the CHECK with the retired values."""
    body = M067.read_text(encoding="utf-8").lower()
    for purpose in RETIRED_PURPOSES:
        assert f"'{purpose}'" in body
