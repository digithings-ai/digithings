"""Pin Olympus Settings remaining-hop predicates to the Python source of truth.

The About panel copies ``proven_remaining_hops``. A fill-only TS predicate
would light ``paper_fill_mirrored`` from an ``api_key`` row the cron now holds.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from digiquant.olympus.kairos.remaining_hops import (
    OVERLAY_RUN_STATUSES,
    REMAINING_HOP_BLOCKER_CODES,
    REMAINING_LIVE_HOPS,
    STRIPE_CHECKOUT_TIERS,
)

pytestmark = pytest.mark.unit

_TS = Path("frontend/olympus/lib/remaining-hops.ts")


def _ts_source() -> str:
    return _TS.read_text(encoding="utf-8")


def test_frontend_remaining_hop_names_match_python() -> None:
    match = re.search(
        r"export const REMAINING_LIVE_HOPS = \[([^\]]+)\] as const",
        _ts_source(),
        re.S,
    )
    assert match is not None
    names = tuple(re.findall(r"'([^']+)'", match.group(1)))
    assert names == REMAINING_LIVE_HOPS


def test_frontend_overlay_run_statuses_match_python() -> None:
    match = re.search(
        r"export const OVERLAY_RUN_STATUSES = new Set\(\[([^\]]+)\]\)",
        _ts_source(),
    )
    assert match is not None
    names = frozenset(re.findall(r"'([^']+)'", match.group(1)))
    assert names == OVERLAY_RUN_STATUSES


def test_frontend_stripe_checkout_tiers_match_python() -> None:
    match = re.search(
        r"export const STRIPE_CHECKOUT_TIERS = new Set\(\[([^\]]+)\]\)",
        _ts_source(),
    )
    assert match is not None
    names = frozenset(re.findall(r"'([^']+)'", match.group(1)))
    assert names == STRIPE_CHECKOUT_TIERS


def test_frontend_stripe_hop_requires_custom_tier() -> None:
    source = _ts_source()
    assert "STRIPE_CHECKOUT_TIERS.has(evidence.plan_tier ?? '')" in source
    assert (
        re.search(
            r"browser_stripe_checkout:\s*evidence\.subscription_status === 'active' && "
            r"evidence\.has_stripe_subscription === true\s*,",
            source,
        )
        is None
    )


def test_frontend_fill_hop_requires_oauth() -> None:
    source = _ts_source()
    assert "paper_fill_mirrored: (evidence.fill_count ?? 0) > 0 && alpaca" in source
    assert (
        re.search(
            r"paper_fill_mirrored:\s*\(evidence\.fill_count \?\? 0\) > 0\s*,",
            source,
        )
        is None
    )


def test_frontend_digest_hop_requires_prefs_and_inbox() -> None:
    source = _ts_source()
    match = re.search(r"digest_email_received:\s*(.*?),\s*\}", source, re.S)
    assert match is not None
    body = re.sub(r"\s+", " ", match.group(1))
    assert "evidence.digest_inbox_confirmed === true" in body
    assert "digestLog" in body
    assert "evidence.daily_digest_enabled === true" in body
    assert (
        re.search(
            r"digest_email_received:\s*evidence\.digest_inbox_confirmed === true && digestLog\s*,",
            source,
        )
        is None
    )


def test_frontend_blocker_codes_match_python() -> None:
    match = re.search(
        r"export const REMAINING_HOP_BLOCKER_CODES = \[([^\]]+)\] as const",
        _ts_source(),
        re.S,
    )
    assert match is not None
    names = tuple(re.findall(r"'([^']+)'", match.group(1)))
    assert names == REMAINING_HOP_BLOCKER_CODES
    source = _ts_source()
    assert "export function remainingHopBlockers" in source
    assert "plan_tier_not_custom" in source
    assert "alpaca_api_key_not_oauth" in source
    assert "overlay_persist_disabled" in source
    assert "digest_inbox_unconfirmed" in source
