"""Unit tests for digivault.tenant_scope — the server-side path_prefix/tenant binding.

Found missing by CodeRabbit's review of promotion PR #2293: `digivault:read` proves a
caller may use these routes at all, but carries no tenant identity, so any caller
holding that scope could name any prefix in D1_DATABASE_MAP, not just their own
corpus's. See tenant_scope.py's module docstring for the full writeup.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from digivault.tenant_scope import (
    TenantCorpusMapError,
    _load_tenant_prefix_map,
    enforce_tenant_path_prefix,
    mapped_tenant_path_prefix,
)
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
def test_load_tenant_prefix_map_raises_when_set_but_unusable(raw: str) -> None:
    """CodeRabbit review of PR #2298 (this module's own PR): a *non-empty* env var
    that produces zero usable entries must not quietly collapse to the same `{}` a
    genuinely-unset one returns — that would let an operator believe multi-tenant
    enforcement is on when a config typo silently turned it off. Each of these is
    "set but broken", not "unset", so each must raise."""
    with pytest.raises(TenantCorpusMapError):
        _load_tenant_prefix_map(raw)


def test_load_tenant_prefix_map_keeps_usable_entries_despite_one_bad_sibling() -> None:
    """The opposite of the above: a config typo for ONE tenant must not take down
    every other tenant's requests — only entries that individually fail to parse are
    dropped (with a warning), and the function only raises when NOTHING survives."""
    raw = '{"digithings": {"vaultPathPrefix": "clients/digithings"}, "broken": {}}'
    assert _load_tenant_prefix_map(raw) == {"digithings": "clients/digithings"}


def test_load_tenant_prefix_map_lowercases_the_slug_key() -> None:
    raw = '{"DigiThings": {"vaultPathPrefix": "clients/digithings"}}'
    assert _load_tenant_prefix_map(raw) == {"digithings": "clients/digithings"}


def test_mapped_tenant_path_prefix_unset() -> None:
    assert mapped_tenant_path_prefix("digithings", raw_map="") is None
    assert mapped_tenant_path_prefix("digithings", raw_map=None) is None


def test_mapped_tenant_path_prefix_resolves() -> None:
    assert mapped_tenant_path_prefix("digithings", raw_map=_MAP) == "clients/digithings"
    assert mapped_tenant_path_prefix("occ", raw_map=_MAP) == "clients/online-compliance-center"


def test_mapped_tenant_path_prefix_unknown_tenant_403() -> None:
    with pytest.raises(HTTPException) as exc:
        mapped_tenant_path_prefix("unknown", raw_map=_MAP)
    assert exc.value.status_code == 403


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


def test_enforce_refuses_a_sub_prefix_of_the_tenants_own_corpus() -> None:
    """CodeRabbit review of PR #2305: comparison is exact, not prefix containment —
    narrowing the requested scope to a subfolder of the tenant's own corpus (e.g.
    "clients/digithings/policies") is refused too, same as a different tenant's
    prefix. This matches the rest of the system: D1_DATABASE_MAP's own lookup in
    server.py's _open_d1_store is an exact dict key match against the corpus-level
    prefix, not a startswith() check — a caller narrowing path_prefix to a subfolder
    was never a supported way to scope a search to that subfolder (use the query
    text for that instead), so this isn't a new restriction, only a clearer 403
    where an unmapped path_prefix used to surface as a less specific 503 further
    downstream. Pinned so the exact-match decision is a recorded choice, not an
    accident of the comparison operator."""
    with pytest.raises(HTTPException) as exc:
        enforce_tenant_path_prefix("digithings", "clients/digithings/policies", raw_map=_MAP)
    assert exc.value.status_code == 403


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


def test_enforce_returns_503_when_map_is_set_but_unusable() -> None:
    """A broken (not merely unset) DIGI_TENANT_CORPUS_MAP must surface as a loud 503
    at the enforcement boundary, same as this service's own D1_DATABASE_MAP config
    errors — never silently pass every request through as if unscoped."""
    with pytest.raises(HTTPException) as exc:
        enforce_tenant_path_prefix("digithings", "clients/digithings", raw_map="{not json")
    assert exc.value.status_code == 503


def test_enforce_refuses_empty_string_tenant_slug_same_as_none() -> None:
    """In-session review of PR #2298: DigiAuthContext.tenant_slug defaults to `""`,
    not `None` (digikey/src/digikey/models.py) — every existing "claimless caller"
    test here used `None`, which happens to collapse to the same refusal via `(tenant_
    slug or "").strip().lower()`, but that equivalence was never pinned on its own."""
    with pytest.raises(HTTPException) as exc:
        enforce_tenant_path_prefix("", "clients/digithings", raw_map=_MAP)
    assert exc.value.status_code == 403


def test_enforce_uses_the_same_md_stripping_normalization_as_the_rest_of_the_service() -> None:
    """CodeRabbit review of PR #2298: an earlier version compared with only
    `strip().strip("/")`, not the shared `normalize_vault_path` (which also strips one
    trailing `.md`). A stray `.md` in the *stored* map entry (an operator typo) would
    then wrongly 403 a caller supplying the correct, already-`.md`-stripped prefix,
    since `resolve_path_prefix` normalizes the caller's own value before it ever
    reaches this comparison. Both sides must use identical normalization."""
    raw = '{"digithings": {"vaultPathPrefix": "clients/digithings.md"}}'
    # The caller's own value, as it would arrive already-normalized by
    # resolve_path_prefix (server.py always passes the resolved, not raw, prefix).
    enforce_tenant_path_prefix("digithings", "clients/digithings", raw_map=raw)
