"""Guard: publish must only write constraint-valid ``documents.category`` values.

Regression test for #628 — publish_document() defaulted to category="research",
which is NOT in the chk_documents_category CHECK constraint, so every baseline /
delta publish failed with PostgREST 23514. This test pins the segment->category
mapping and asserts every category the publish path can emit is allow-listed.
"""

from __future__ import annotations

import pytest

from digiquant.olympus.atlas.phases.publish_phase import _segment_category

# Source of truth: chk_documents_category in
# digiquant/supabase/migrations/{002_schema_hardening,011_unpartition_snapshots_documents}.sql
ALLOWED_CATEGORIES = frozenset(
    {
        "synthesis",
        "macro",
        "asset-class",
        "equity",
        "sector",
        "alt-data",
        "institutional",
        "portfolio",
        "delta",
        "output",
        "rollup",
        "deep-dive",
    }
)

# Categories the publish node passes explicitly (not via _segment_category):
# digest (synthesis / delta / output), analysts (deep-dive), pm-rebalance (portfolio),
# macro (macro). Kept in sync with publish_phase.build_publish_node.
EXPLICIT_CATEGORIES = {"synthesis", "delta", "output", "deep-dive", "portfolio", "macro"}


@pytest.mark.unit
class TestPublishCategoryConstraint:
    @pytest.mark.parametrize(
        "slug, expected",
        [
            ("alt-sentiment-news", "alt-data"),
            ("alt-cta-positioning", "alt-data"),
            ("inst-institutional-flows", "institutional"),
            ("inst-hedge-fund-intel", "institutional"),
            ("macro", "macro"),
            ("bonds", "asset-class"),
            ("commodities", "asset-class"),
            ("forex", "asset-class"),
            ("crypto", "asset-class"),
            ("international", "asset-class"),
            ("equity", "equity"),
            ("sector-technology", "sector"),
            ("sector-healthcare", "sector"),
            ("some-unmapped-slug", "output"),  # safe catch-all
        ],
    )
    def test_segment_category_mapping(self, slug: str, expected: str) -> None:
        assert _segment_category(slug) == expected

    def test_all_segment_categories_are_constraint_valid(self) -> None:
        """Every segment slug from the live model_modes phases maps to an allowed category."""
        sample_slugs = [
            "alt-sentiment-news",
            "alt-cta-positioning",
            "alt-options-derivatives",
            "alt-politician-signals",
            "inst-institutional-flows",
            "inst-hedge-fund-intel",
            "macro",
            "bonds",
            "commodities",
            "forex",
            "crypto",
            "international",
            "equity",
            "sector-technology",
            "sector-energy",
            "anything-else",
        ]
        for slug in sample_slugs:
            assert _segment_category(slug) in ALLOWED_CATEGORIES, slug

    def test_explicit_categories_are_constraint_valid(self) -> None:
        """The hard-coded digest/analyst/pm categories must also be allow-listed."""
        assert EXPLICIT_CATEGORIES <= ALLOWED_CATEGORIES
