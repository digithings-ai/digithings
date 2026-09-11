"""Corpus parity pin: digigraph and digivault resolve the same production map (refs #3854).

PIN-ONLY — no behavior change. Both sides already implement their half
(digigraph ``corpus_routing.resolve_corpus_override`` is authoritative-map mode;
digivault ``tenant_scope.mapped_tenant_path_prefix`` fails closed). These tests
pin the shared production map string so a drift on either side goes red.

Source truth: ``digigraph/src/digigraph/corpus_routing.py`` (map set +
unmapped/empty tenant → empty ``TenantCorpusOverride()``; map unset → headers
select corpus) and ``digivault/src/digivault/tenant_scope.py``
(``mapped_tenant_path_prefix``: map unset → ``None``; known → normalized prefix;
unknown/empty → ``HTTPException(403)``; set-but-broken → ``503``).
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from digigraph.corpus_routing import (
    TenantCorpusMapError,
    TenantCorpusOverride,
    load_tenant_corpus_map,
    resolve_corpus_override,
)
from digivault.tenant_scope import mapped_tenant_path_prefix
from fastapi import HTTPException

pytestmark = pytest.mark.unit

#: SAME raw map string used in production — verbatim from
#: ``infra/digichat-release/compose.profile-a-bundle.override.yml:11`` and
#: ``cloudflare/digithings-stack-cloudflare/wrangler.toml`` ``DIGI_TENANT_CORPUS_MAP``.
_RAW_MAP = (
    '{"digithings":{"digisearchIndex":"digithings_docs",'
    '"vaultPathPrefix":"clients/digithings"},'
    '"occ":{"digisearchIndex":"occ_help",'
    '"vaultPathPrefix":"clients/online-compliance-center"}}'
)

_EXPECTED = {
    "digithings": ("digithings_docs", "clients/digithings"),
    "occ": ("occ_help", "clients/online-compliance-center"),
}


@pytest.mark.parametrize(("slug", "index", "prefix"), [(s, *v) for s, v in _EXPECTED.items()])
def test_mapped_tenants_resolve_index_and_prefix_on_both_sides(
    slug: str, index: str, prefix: str
) -> None:
    """Mapped slugs resolve the same index + prefix through both services."""
    table = load_tenant_corpus_map(_RAW_MAP)
    override = resolve_corpus_override(tenant_slug=slug, corpus_map=table)
    assert (override.digisearch_index, override.vault_path_prefix) == (index, prefix)
    assert mapped_tenant_path_prefix(slug, raw_map=_RAW_MAP) == prefix
    assert mapped_tenant_path_prefix(slug, raw_map=_RAW_MAP) == override.vault_path_prefix


@pytest.mark.parametrize("slug", ["no-such-tenant", "", None])
def test_unmapped_slug_asymmetry_is_intentional(slug: str | None) -> None:
    """Unmapped/empty tenant: digigraph clears to an empty override, digivault 403s.

    The asymmetry is INTENTIONAL (track-G brief ruling — do not "fix" one side
    to match the other): digigraph must not fall through to a client-supplied
    index, while digivault refuses the request outright.
    """
    table = load_tenant_corpus_map(_RAW_MAP)
    assert resolve_corpus_override(tenant_slug=slug, corpus_map=table) == TenantCorpusOverride()
    with pytest.raises(HTTPException) as excinfo:
        mapped_tenant_path_prefix(slug, raw_map=_RAW_MAP)
    assert excinfo.value.status_code == 403


def test_map_unset_digigraph_honors_headers_digivault_returns_none() -> None:
    """Genuinely-unset map: single-tenant mode on both sides."""
    headers = {"x-digi-corpus-index": "custom_idx", "x-digi-vault-prefix": "clients/custom"}
    override = resolve_corpus_override(headers=headers, tenant_slug=None, corpus_map={})
    assert (override.digisearch_index, override.vault_path_prefix) == (
        "custom_idx",
        "clients/custom",
    )
    assert mapped_tenant_path_prefix("digithings", raw_map="") is None


@pytest.mark.parametrize("raw", ["not json", "[]"])
def test_broken_map_fails_closed_on_both_sides(raw: str) -> None:
    """Set-but-broken map is never "unset": digigraph raises, digivault 503s."""
    with pytest.raises(TenantCorpusMapError):
        load_tenant_corpus_map(raw)
    with pytest.raises(HTTPException) as excinfo:
        mapped_tenant_path_prefix("digithings", raw_map=raw)
    assert excinfo.value.status_code == 503
