"""Unit tests for digivault.tenant_scope — the server-side path_prefix/tenant binding.

Found missing by CodeRabbit's review of promotion PR #2293: `digivault:read` proves a
caller may use these routes at all, but carries no tenant identity, so any caller
holding that scope could name any prefix in D1_DATABASE_MAP, not just their own
corpus's. See tenant_scope.py's module docstring for the full writeup.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from digivault.tenant_scope import _load_tenant_prefix_map, enforce_tenant_path_prefix
from fastapi import HTTPException

_MAP = (
    '{"digithings": {"vaultPathPrefix": "clients/digithings", "digisearchIndex": "d"},'
    ' "occ": {"vaultPathPrefix": "clients/online-compliance-center"}}'
)

pytestmark = pytest.mark.unit


# ── _load_tenant_prefix_map ──────────────────────────────────────────────────
def test_load_tenant_prefix_map_empty_when_unset() -> None:
    assert _load_tenant_prefix_map("") == {}
    assert _load_tenant_prefix_map(None) == {}
    assert _load_tenant_prefix_map("   ") == {}


def test_load_tenant_prefix_map_parses_vault_path_prefix_ignoring_other_keys() -> None:
    assert _load_tenant_prefix_map(_MAP) == {
        "digithings": "clients/digithings",
        "occ": "clients/online-compliance-center",
    }


def test_load_tenant_prefix_map_accepts_snake_case_key_too() -> None:
    """digigraph's own corpus_routing.py accepts both `vaultPathPrefix` and
    `vault_path_prefix` — this module must parse the same env var identically."""
    raw = '{"digithings": {"vault_path_prefix": "clients/digithings"}}'
    assert _load_tenant_prefix_map(raw) == {"digithings": "clients/digithings"}


def test_load_tenant_prefix_map_normalizes_slashes() -> None:
    raw = '{"digithings": {"vaultPathPrefix": "/clients/digithings/"}}'
    assert _load_tenant_prefix_map(raw) == {"digithings": "clients/digithings"}


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '{"digithings": "not-an-object"}',
        '{"digithings": {}}',
    ],
)
def test_load_tenant_prefix_map_tolerates_malformed_input(raw: str) -> None:
    """Malformed config must never raise — a typo for one tenant must not take down
    every other tenant's requests, and this must never crash a request or startup."""
    _load_tenant_prefix_map(raw)  # must not raise


def test_load_tenant_prefix_map_lowercases_the_slug_key() -> None:
    raw = '{"DigiThings": {"vaultPathPrefix": "clients/digithings"}}'
    assert _load_tenant_prefix_map(raw) == {"digithings": "clients/digithings"}


# ── enforce_tenant_path_prefix ───────────────────────────────────────────────
def test_enforce_is_noop_when_map_unset() -> None:
    """Single-tenant deployments (local dev, self-hosted, most of this test suite)
    never set DIGI_TENANT_CORPUS_MAP — must see zero behavior change."""
    enforce_tenant_path_prefix(None, "clients/anything", raw_map="")
    enforce_tenant_path_prefix("some-tenant", "clients/anything", raw_map=None)


def test_enforce_is_noop_when_no_prefix_requested() -> None:
    """A None/empty path_prefix is a different, pre-existing code path's job
    ("path_prefix is required") — this function must not interfere with it."""
    enforce_tenant_path_prefix("digithings", None, raw_map=_MAP)
    enforce_tenant_path_prefix("digithings", "", raw_map=_MAP)


def test_enforce_allows_the_tenants_own_prefix() -> None:
    enforce_tenant_path_prefix("digithings", "clients/digithings", raw_map=_MAP)
    enforce_tenant_path_prefix("occ", "clients/online-compliance-center", raw_map=_MAP)


def test_enforce_allows_unnormalized_variants_of_the_same_prefix() -> None:
    enforce_tenant_path_prefix("digithings", "/clients/digithings/", raw_map=_MAP)


def test_enforce_refuses_another_tenants_prefix() -> None:
    """The exact cross-tenant scenario CodeRabbit's review flagged: a digithings
    caller naming the occ corpus's prefix."""
    with pytest.raises(HTTPException) as exc:
        enforce_tenant_path_prefix("digithings", "clients/online-compliance-center", raw_map=_MAP)
    assert exc.value.status_code == 403


def test_enforce_refuses_when_tenant_slug_is_unmapped() -> None:
    """Once the map is configured at all (multi-tenant mode is on), a tenant absent
    from it has no authorized prefix — any explicit prefix must be refused, not
    silently allowed through."""
    with pytest.raises(HTTPException) as exc:
        enforce_tenant_path_prefix("some-other-tenant", "clients/digithings", raw_map=_MAP)
    assert exc.value.status_code == 403


def test_enforce_refuses_when_tenant_slug_is_none_but_map_is_configured() -> None:
    """An unauthenticated/claimless caller must not be treated as unscoped once the
    deployment is in multi-tenant mode."""
    with pytest.raises(HTTPException) as exc:
        enforce_tenant_path_prefix(None, "clients/digithings", raw_map=_MAP)
    assert exc.value.status_code == 403
