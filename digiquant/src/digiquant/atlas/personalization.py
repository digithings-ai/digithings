"""Personalize a SnapshotEnvelope for a logged-in user.

This module turns the global Atlas digest into a per-user view by applying
:class:`digiquant.profiles.investment_profile.InvestmentProfile` and
:class:`digiquant.profiles.asset_preferences.AssetPreferences` to a
:class:`digiquant.atlas.snapshot.SnapshotEnvelope`. It is the read-time helper
the Atlas BFF / dashboard calls before rendering — the upstream pipeline still
writes one canonical row per day to ``daily_snapshots`` (Phase 7), and this
function adapts that row for the calling user.

Issue: `#312 <https://github.com/digithings-ai/digithings/issues/312>`_.

Return shape — a sibling dataclass, not a v2 envelope
-----------------------------------------------------
The task brief offered two designs. We pick the **sibling dataclass**:

    >>> result: PersonalizedSnapshot = personalize_snapshot(env, profile=p)
    >>> result.envelope          # SnapshotEnvelope, schema_version unchanged
    >>> result.excluded_count    # int — items dropped by exclusion rules
    >>> result.rank_changes      # list[(label, old_index, new_index)]

Why not stick a ``personalized_for`` block on the envelope?
:class:`SnapshotEnvelope`, :class:`DigestPayload`, :class:`ActionableItem`,
:class:`RiskItem` are all ``model_config = ConfigDict(extra="forbid")`` and
the project convention is to **not** bump ``SCHEMA_VERSION`` for additive
read-time decoration. The dataclass keeps the wire contract immutable
(important: the same envelope JSON is reused for caching, audit, and the
schema-export drift test) while still surfacing diagnostics for QA + UI.

Filtering + ranking semantics
-----------------------------
Anonymous (both ``profile`` and ``preferences`` are ``None``)
    Pass-through: returns ``PersonalizedSnapshot(envelope=envelope,
    excluded_count=0, rank_changes=[])`` — the envelope object is the same
    instance the caller passed in.

``preferences.excluded_tickers``
    Drop list-shaped items (``actionable_summary``, ``risk_radar``,
    ``material_findings``) whose ``label`` / ``rationale`` / ``trigger`` /
    ``summary`` mention any excluded ticker. Ticker matching is a
    word-boundary uppercase regex (``\\b[A-Z]{1,5}\\b``) — coarse but
    documented: "USA", "UK", "API" can collide with real tickers. The
    upside is determinism and zero-dependency.

    Prose blocks (``headline``, ``market_regime_snapshot``, etc.) are
    **not** rewritten — string surgery on narrative summaries is brittle
    and the personalization is consumed by a UI that renders structured
    items as the primary affordance anyway.

``preferences.custom_universe``
    Reorder ``actionable_summary`` so items mentioning a custom-universe
    ticker move to the front while preserving relative order within the
    "matched" and "unmatched" partitions. Each move is reported in
    ``rank_changes`` so the UI can render a "boosted by your watchlist"
    badge if it wants to.

``profile.risk_tolerance``
    ``conservative`` drops actionable items with ``priority < 3`` (low
    priority = aggressive trade ideas in the upstream schema, see
    ``ActionableItem`` field rationale).  ``moderate`` is a pass-through.
    ``aggressive`` is a pass-through (everything stays).

``profile.esg_preference`` + (``profile.excluded_sectors`` or
``preferences.excluded_sectors``)
    ``strict`` drops items whose ``label`` or ``rationale`` (lower-cased)
    contains an excluded sector substring. ``tilt`` and ``none`` are
    pass-through here — ``tilt`` is intended to drive *weighting* in
    Hermes / Kairos, not visibility in Atlas.

Performance
-----------
Issue requirement: < 100 ms for a typical snapshot.  The implementation is
O(N · (T + S)) where N = number of items, T = number of excluded tickers,
S = number of excluded sectors — all small constants in practice. We
mutate a single dict copy of the envelope (``model_dump`` once,
``model_validate`` once), avoiding per-item ``model_copy(deep=True)``. The
unit test budgets 200 ms for a 100-item snapshot to stay quiet on noisy
CI runners while still catching catastrophic regressions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from digiquant.atlas.snapshot import SnapshotEnvelope
from digiquant.profiles.asset_preferences import AssetPreferences
from digiquant.profiles.investment_profile import InvestmentProfile

# Word-boundary upper-case 1..5 chars — captures "AAPL", "XOM", "TSLA",
# also "USA", "UK". Trade-off documented in the module docstring.
_TICKER_RE: re.Pattern[str] = re.compile(r"\b[A-Z]{1,5}\b")


@dataclass(frozen=True)
class PersonalizedSnapshot:
    """Result of :func:`personalize_snapshot`.

    Attributes
    ----------
    envelope
        The personalized :class:`SnapshotEnvelope`. ``schema_version`` is
        identical to the input envelope's. For an anonymous call (both
        ``profile`` and ``preferences`` are ``None``) this is the *same*
        instance the caller passed in.
    excluded_count
        Total number of list-shaped items dropped by exclusion rules across
        ``actionable_summary``, ``risk_radar``, and ``material_findings``.
        Useful as a diagnostic ("we filtered N items for you") and for
        observability.
    rank_changes
        For each item moved by the custom-universe boost, a tuple
        ``(label, old_index, new_index)`` — ``label`` is the
        ``ActionableItem.label`` that moved.  Items that were not moved
        do not appear here. Empty list when no boost applied.
    """

    envelope: SnapshotEnvelope
    excluded_count: int = 0
    rank_changes: list[tuple[str, int, int]] = field(default_factory=list)


def personalize_snapshot(
    envelope: SnapshotEnvelope,
    *,
    profile: InvestmentProfile | None = None,
    preferences: AssetPreferences | None = None,
) -> PersonalizedSnapshot:
    """Return a copy of ``envelope`` filtered + ranked for the given user.

    See the module docstring for the full filtering and ranking semantics.

    Parameters
    ----------
    envelope
        The Atlas snapshot envelope, typically loaded from
        ``daily_snapshots`` via :meth:`SnapshotEnvelope.from_supabase_row`.
    profile
        Optional investment profile. ``None`` = anonymous user.
    preferences
        Optional asset preferences. ``None`` = anonymous user.

    Returns
    -------
    PersonalizedSnapshot
        Wraps the personalized envelope plus diagnostics. The envelope's
        ``schema_version`` is identical to the input's.
    """
    # Fast path: anonymous user — return the envelope unchanged. We return
    # the same instance (no clone) because Pydantic v2 BaseModel is
    # effectively immutable in our config (frozen=False but extra=forbid
    # and no setters in the surrounding code).
    if profile is None and preferences is None:
        return PersonalizedSnapshot(envelope=envelope)

    # Collect the rule sets once. Lookups inside the hot loop are sets.
    excluded_tickers: frozenset[str] = (
        frozenset(preferences.excluded_tickers) if preferences is not None else frozenset()
    )
    custom_universe: tuple[str, ...] = (
        tuple(preferences.custom_universe) if preferences is not None else ()
    )

    # Sector exclusions union both sources, preserving order. Profile +
    # preferences are already lower-cased + de-duplicated by their validators.
    sector_sources: list[str] = []
    if profile is not None and profile.esg_preference == "strict":
        sector_sources.extend(profile.excluded_sectors)
    if preferences is not None:
        sector_sources.extend(preferences.excluded_sectors)
    excluded_sectors: list[str] = list(dict.fromkeys(sector_sources))

    drop_low_priority: bool = profile is not None and profile.risk_tolerance == "conservative"
    apply_strict_esg: bool = (
        profile is not None and profile.esg_preference == "strict" and bool(excluded_sectors)
    )

    # Dump once — mutating the dict in place is dramatically faster than
    # ``model_copy(deep=True)`` + per-list rebuilds, especially with 100+
    # items.  ``model_dump(mode="python")`` keeps date / datetime objects
    # as Python instances so re-validation is cheap.
    payload: dict[str, Any] = envelope.model_dump(mode="python")
    digest: dict[str, Any] = payload["digest"]

    excluded_count: int = 0

    # ── actionable_summary: exclusion + ESG drop + low-priority drop ───
    actionable_in: list[dict[str, Any]] = digest.get("actionable_summary", [])
    actionable_kept: list[dict[str, Any]] = []
    for item in actionable_in:
        if _item_mentions_excluded_ticker(item, excluded_tickers, ("label", "rationale")):
            excluded_count += 1
            continue
        if apply_strict_esg and _item_mentions_excluded_sector(
            item, excluded_sectors, ("label", "rationale")
        ):
            excluded_count += 1
            continue
        if drop_low_priority and int(item.get("priority", 0)) < 3:
            excluded_count += 1
            continue
        actionable_kept.append(item)

    # ── custom-universe boost: stable partition (matched first) ────────
    rank_changes: list[tuple[str, int, int]] = []
    if custom_universe:
        actionable_kept, rank_changes = _boost_by_custom_universe(actionable_kept, custom_universe)

    digest["actionable_summary"] = actionable_kept

    # ── risk_radar: exclusion + ESG drop ───────────────────────────────
    risk_in: list[dict[str, Any]] = digest.get("risk_radar", [])
    risk_kept: list[dict[str, Any]] = []
    for item in risk_in:
        if _item_mentions_excluded_ticker(item, excluded_tickers, ("label", "trigger")):
            excluded_count += 1
            continue
        if apply_strict_esg and _item_mentions_excluded_sector(
            item, excluded_sectors, ("label", "trigger")
        ):
            excluded_count += 1
            continue
        risk_kept.append(item)
    digest["risk_radar"] = risk_kept

    # ── material_findings: exclusion + ESG drop ────────────────────────
    findings_in: list[dict[str, Any]] = digest.get("material_findings", [])
    findings_kept: list[dict[str, Any]] = []
    for item in findings_in:
        if _item_mentions_excluded_ticker(item, excluded_tickers, ("label", "summary")):
            excluded_count += 1
            continue
        if apply_strict_esg and _item_mentions_excluded_sector(
            item, excluded_sectors, ("label", "summary")
        ):
            excluded_count += 1
            continue
        findings_kept.append(item)
    digest["material_findings"] = findings_kept

    # Re-validate so callers get a typed envelope back. If we have built up
    # a structurally invalid digest (we shouldn't — exclusion only drops
    # whole items, never reshapes one), pydantic raises with a clear path.
    new_envelope = SnapshotEnvelope.model_validate(payload)

    return PersonalizedSnapshot(
        envelope=new_envelope,
        excluded_count=excluded_count,
        rank_changes=rank_changes,
    )


# ─── Internals ──────────────────────────────────────────────────────────────


def _extract_tickers(text: str) -> set[str]:
    """Pull candidate tickers out of free text. Coarse, documented above."""
    if not text:
        return set()
    return set(_TICKER_RE.findall(text))


def _item_mentions_excluded_ticker(
    item: dict[str, Any],
    excluded: frozenset[str],
    fields: tuple[str, ...],
) -> bool:
    if not excluded:
        return False
    for field_name in fields:
        value = item.get(field_name) or ""
        if not isinstance(value, str):
            continue
        candidates = _extract_tickers(value)
        if candidates & excluded:
            return True
    return False


def _item_mentions_excluded_sector(
    item: dict[str, Any],
    sectors: list[str],
    fields: tuple[str, ...],
) -> bool:
    if not sectors:
        return False
    for field_name in fields:
        value = item.get(field_name) or ""
        if not isinstance(value, str):
            continue
        haystack = value.lower()
        for sector in sectors:
            if sector and sector in haystack:
                return True
    return False


def _boost_by_custom_universe(
    items: list[dict[str, Any]],
    universe: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[tuple[str, int, int]]]:
    """Stable partition: items mentioning a universe ticker move to the front.

    Within each partition (matched / unmatched) the original relative order
    is preserved — a stable reorder, not a sort.

    Returns
    -------
    (reordered_items, rank_changes)
        ``rank_changes`` lists tuples ``(label, old_idx, new_idx)`` for any
        item whose position changed. Items that did not move are omitted
        for compactness.
    """
    if not items or not universe:
        return items, []

    universe_set = frozenset(universe)
    matched: list[tuple[int, dict[str, Any]]] = []
    unmatched: list[tuple[int, dict[str, Any]]] = []
    for idx, item in enumerate(items):
        text = " ".join(
            str(item.get(name, "")) for name in ("label", "rationale") if item.get(name)
        )
        if _extract_tickers(text) & universe_set:
            matched.append((idx, item))
        else:
            unmatched.append((idx, item))

    if not matched:
        # Nothing to boost — preserve original order verbatim.
        return items, []

    reordered: list[dict[str, Any]] = [item for _, item in matched] + [
        item for _, item in unmatched
    ]
    rank_changes: list[tuple[str, int, int]] = []
    for new_idx, (old_idx, item) in enumerate(matched + unmatched):
        if new_idx != old_idx:
            label = str(item.get("label", ""))
            rank_changes.append((label, old_idx, new_idx))

    return reordered, rank_changes


__all__ = [
    "PersonalizedSnapshot",
    "personalize_snapshot",
]
