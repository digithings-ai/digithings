"""Pins the frozen uuid5 namespaces so the legacy seed strings cannot creep back (#4295).

Each deterministic id in the dashboard is derived from a namespace UUID that was
originally ``uuid5(NAMESPACE_URL, "digithings.olympus.<name>")``. Migration 096 and
friends seed the *derived* values into the database, and every house writer stamps
them onto rows with a foreign key to ``workspaces(id)``. So the namespace UUID is
identity, not a package path: it must keep producing exactly the same derived ids
even though the seed string is gone from live code.

This test pins both halves of that contract for each namespace:

- the constant is the frozen UUID literal, and
- the literal still equals ``uuid5(NAMESPACE_URL, <legacy seed>)``,

so an accidental re-key (changing the literal, or reintroducing a different seed)
fails here instead of orphaning ledger rows via an FK violation. It also greps
``digiquant/src`` to assert no legacy seed expression remains.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from digiquant.dashboard.attention_plan import _PLAN_NS
from digiquant.dashboard.profile_config import (
    _PROFILE_VERSION_NS,
    house_profile_config,
)
from digiquant.dashboard.research_corpus import _CORPUS_VERSION_NS
from digiquant.dashboard.research_retrieval.planner import (
    _ATTENTION_DECISION_NS,
    _ATTENTION_EVALUATION_NS,
    _ATTENTION_PLAN_NS,
)
from digiquant.dashboard.tenancy import (
    _TENANCY_NAMESPACE,
    house_workspace_id,
    system_workspace_id,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]

# (constant, frozen literal, legacy seed the literal must keep reproducing)
_FROZEN_NAMESPACES: tuple[tuple[UUID, str, str], ...] = (
    (
        _PROFILE_VERSION_NS,
        "6b517df3-6212-5610-a117-61ab09e196a2",
        "digithings.olympus.profile_config",
    ),
    (_PLAN_NS, "b3161865-af82-5871-b1ad-729f26f0bd4d", "digithings.olympus.attention_plan"),
    (
        _CORPUS_VERSION_NS,
        "a0edd75e-2d5a-5496-8cf4-7c35dd1ef008",
        "digithings.olympus.research_corpus",
    ),
    (
        _ATTENTION_PLAN_NS,
        "55ee801e-f006-5a47-bcf0-8b2f10293c29",
        "digithings.olympus.research_attention_plan",
    ),
    (
        _ATTENTION_DECISION_NS,
        "f40d03e4-0306-56fd-a1f7-9d842267e7d3",
        "digithings.olympus.research_attention_decision",
    ),
    (
        _ATTENTION_EVALUATION_NS,
        "b1983998-d185-54bb-a236-8bea9f9c7592",
        "digithings.olympus.research_attention_evaluation",
    ),
    (_TENANCY_NAMESPACE, "f6170a00-e195-5e92-8c41-2178302e37a8", "digithings.olympus.tenancy"),
)

_LEGACY_SEED_RE = re.compile(r"""uuid5\(\s*NAMESPACE_URL\s*,\s*['"]digithings\.olympus""")


@pytest.mark.parametrize(("constant", "literal", "seed"), _FROZEN_NAMESPACES)
def test_namespace_is_frozen_literal(constant: UUID, literal: str, seed: str) -> None:
    assert constant == UUID(literal)


@pytest.mark.parametrize(("constant", "literal", "seed"), _FROZEN_NAMESPACES)
def test_frozen_literal_equals_legacy_seed(constant: UUID, literal: str, seed: str) -> None:
    assert constant == uuid5(NAMESPACE_URL, seed)


def test_no_legacy_olympus_seed_remains_in_digiquant_src() -> None:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "digiquant" / "src").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _LEGACY_SEED_RE.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    assert not offenders, f"legacy uuid5 seed expression(s) still in digiquant/src: {offenders}"


def test_derived_tenancy_ids_are_unchanged() -> None:
    assert system_workspace_id() == UUID("1105372f-4109-5815-be5a-21091ccfc8ad")
    assert house_workspace_id() == UUID("6b753576-ced9-5319-9bfa-c5d0aacd9319")


def test_derived_house_profile_id_is_unchanged() -> None:
    assert house_profile_config().version_id == UUID("4ee97e91-7b5b-5a50-b562-37d34250b0f9")
