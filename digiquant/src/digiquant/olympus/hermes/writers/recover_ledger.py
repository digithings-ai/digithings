"""Recover a ledger commit from an already-booked positions row (#3330, #3426).

Use when booking wrote ``positions`` / ``nav_history`` but the commit-run
document insert died. Reads the decided book; does not re-size or call an LLM.
When a head commit already exists, does not append again: matching approved
weights publish only the missing manifest; otherwise ``conflict`` unless
``force_recommit``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from digiquant.olympus.atlas.dashboard_digest import portfolio_preferences_static
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState
from digiquant.olympus.atlas.supabase_io import (
    SupabaseClient,
    load_prior_book,
    prior_book_current_weights,
    publish_document,
    query_price_deltas,
)
from digiquant.olympus.hermes.turnover import mark_to_market_weights
from digiquant.olympus.hermes.writers.commit_io import (
    load_commit_manifests,
    resolve_prior_commit,
    weights_fingerprint,
)
from digiquant.olympus.hermes.writers.ledger_io import (
    _CASH,
    APPROVED_TARGETS,
    COMMITS,
    LedgerAppend,
    _execute,
    _head_by_symbol,
    _heads,
    _rows_for_date,
    _symbol,
    append_commit_chain,
)
from digiquant.olympus.tenancy import resolved_workspace_id

logger = logging.getLogger(__name__)

_PORTFOLIO_JSON = Path(__file__).resolve().parents[2] / "atlas" / "config" / "portfolio.json"
RecoveryStatus = Literal["dry_run", "committed", "already_committed", "no_book", "conflict"]


@dataclass(frozen=True)
class LedgerRecovery:
    """Outcome of one recover attempt. ``commit_id`` is set when a chain exists."""

    run_date: date
    status: RecoveryStatus
    commit_id: str | None
    source_run_id: str | None
    weights: dict[str, float]
    cash_pct: float
    nav: float
    message: str


def _coerce_pct(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _load_book(
    *, client: SupabaseClient, run_date: date, workspace_id: str | None
) -> tuple[dict[str, float], float, float]:
    """Non-cash weights (percent), cash_pct, nav from the already-booked day."""
    date_str = run_date.isoformat()
    scoped = str(resolved_workspace_id(workspace_id))
    pos_resp = _execute(
        client.table("positions")
        .select("ticker, weight_pct")
        .eq("date", date_str)
        .eq("workspace_id", scoped)
    )
    weights: dict[str, float] = {}
    cash_pct = 0.0
    for row in pos_resp.data or []:
        ticker = _symbol(row.get("ticker"))
        pct = round(_coerce_pct(row.get("weight_pct")), 4)
        if not ticker:
            continue
        if ticker == _CASH:
            cash_pct = pct
            continue
        if pct > 0:
            weights[ticker] = pct
    nav_resp = _execute(
        client.table("nav_history")
        .select("nav, cash_pct")
        .eq("date", date_str)
        .eq("workspace_id", scoped)
    )
    nav_rows = list(nav_resp.data or [])
    nav = _coerce_pct(nav_rows[0].get("nav")) if nav_rows else 0.0
    if nav_rows and cash_pct <= 0:
        cash_pct = round(_coerce_pct(nav_rows[0].get("cash_pct")), 4)
    return weights, cash_pct, nav


def _prior_current_weights(
    *, client: SupabaseClient, run_date: date, workspace_id: str | None
) -> dict[str, float]:
    """Mark-to-market prior book — the same baseline preflight feeds the ledger."""
    prior = load_prior_book(client, run_date, workspace_id=workspace_id)
    current = prior_book_current_weights(list(prior))
    held = tuple(ticker for ticker in current if _symbol(ticker) != _CASH)
    deltas = query_price_deltas(client=client, tickers=held, run_date=run_date) if held else {}
    return mark_to_market_weights(current, deltas)


def _decision_log_rows(*, client: SupabaseClient, run_date: date) -> int:
    resp = _execute(
        client.table("decision_log").select("ticker").eq("run_date", run_date.isoformat())
    )
    return len(list(resp.data or []))


def _house_preferences(*, current_weights: dict[str, float]) -> dict[str, object]:
    prefs: dict[str, object] = dict(portfolio_preferences_static(_PORTFOLIO_JSON))
    prefs["current_weights"] = current_weights
    return prefs


def _recovery_state(
    *,
    run_date: date,
    source_run_id: UUID,
    current_weights: dict[str, float],
    workspace_id: str | None,
) -> AtlasResearchState:
    return AtlasResearchState(
        run_id=source_run_id,
        run_type="delta",
        run_date=run_date,
        config=AtlasConfigBundle(
            preferences=_house_preferences(current_weights=current_weights),
            workspace_id=workspace_id,
        ),
    )


def _manifest(
    *,
    source_run_id: str,
    weights: dict[str, float],
    cash_pct: float,
    nav: float,
    ledger: LedgerAppend,
    decision_log_rows: int,
    commit_seq: int,
    supersedes: list[str],
) -> dict[str, object]:
    booked = {**{k: round(v, 4) for k, v in sorted(weights.items())}}
    return {
        "schema_version": "1.6",
        "source_run_id": source_run_id,
        "status": "committed",
        "recovery": "append_from_existing_book",
        "weights_fingerprint": weights_fingerprint(weights),
        "weights": booked,
        "cash_pct": cash_pct,
        "nav": nav,
        "decision_log_rows": decision_log_rows,
        "commit_seq": commit_seq,
        "supersedes": list(supersedes),
        "pruned_tickers": [],
        "ledger_commit_id": ledger.commit_id,
        "ledger_frozen_symbols": list(ledger.frozen_symbols),
        "ledger_unpriced_symbols": list(ledger.unpriced_symbols),
    }


def _publish_manifest(
    *,
    client: SupabaseClient,
    state: AtlasResearchState,
    manifest: dict[str, object],
) -> None:
    date_str = state.run_date.isoformat()
    workspace_id = getattr(state.config, "workspace_id", None)
    publish_document(
        client=client,
        document_key=f"commit-run/{state.run_id}",
        payload=manifest,
        doc_type="Commit Run",
        run_type=state.run_type,
        title=f"Commit Run {date_str}",
        date_str=date_str,
        category="portfolio",
        segment="commit_run",
        workspace_id=workspace_id,
    )


def _prior_manifest_fingerprints(manifests: list[dict[str, object]]) -> list[str]:
    return [str(m.get("weights_fingerprint")) for m in manifests if m.get("weights_fingerprint")]


def _approved_matches_book(
    *,
    client: SupabaseClient,
    run_date: date,
    workspace_id: str | None,
    weights: dict[str, float],
    cash_pct: float,
) -> bool:
    approved = _rows_for_date(
        client=client, table=APPROVED_TARGETS, run_date=run_date, workspace_id=workspace_id
    )
    by_symbol = _head_by_symbol(_heads(approved))
    needed = {_symbol(ticker): round(float(pct), 4) for ticker, pct in weights.items()}
    needed[_CASH] = round(float(cash_pct), 4)
    if not needed:
        return False
    for symbol, pct in needed.items():
        row = by_symbol.get(symbol)
        if row is None:
            return False
        try:
            got = round(float(row.get("approved_weight") or 0.0) * 100.0, 4)
        except (TypeError, ValueError):
            return False
        if abs(got - pct) > 1e-4:
            return False
    for symbol, row in by_symbol.items():
        if symbol in needed:
            continue
        try:
            extra = float(row.get("approved_weight") or 0.0)
        except (TypeError, ValueError):
            extra = 0.0
        if abs(extra) > 1e-9:
            return False
    return True


def _outcome(
    *,
    run_date: date,
    status: RecoveryStatus,
    commit_id: str | None,
    source_run_id: str | None,
    weights: dict[str, float],
    cash_pct: float,
    nav: float,
    message: str,
) -> LedgerRecovery:
    return LedgerRecovery(
        run_date=run_date,
        status=status,
        commit_id=commit_id,
        source_run_id=source_run_id,
        weights=weights,
        cash_pct=cash_pct,
        nav=nav,
        message=message,
    )


def _publish_missing_manifest(
    *,
    client: SupabaseClient,
    run_date: date,
    overlay: str | None,
    head_id: str,
    manifests: list[dict[str, object]],
    next_seq: int,
    weights: dict[str, float],
    cash_pct: float,
    nav: float,
) -> str:
    """Write the commit-run document for an existing head. Returns ``source_run_id``."""
    source_run_id = uuid4()
    state = _recovery_state(
        run_date=run_date,
        source_run_id=source_run_id,
        current_weights=_prior_current_weights(
            client=client, run_date=run_date, workspace_id=overlay
        ),
        workspace_id=overlay,
    )
    ledger = LedgerAppend(commit_id=head_id, frozen_symbols=[], unpriced_symbols=[])
    n_decisions = _decision_log_rows(client=client, run_date=run_date)
    _publish_manifest(
        client=client,
        state=state,
        manifest=_manifest(
            source_run_id=str(source_run_id),
            weights=weights,
            cash_pct=cash_pct,
            nav=nav,
            ledger=ledger,
            decision_log_rows=n_decisions,
            commit_seq=next_seq,
            supersedes=_prior_manifest_fingerprints(manifests),
        ),
    )
    return str(source_run_id)


def recover_ledger_from_book(
    *,
    client: SupabaseClient,
    run_date: date,
    apply: bool = False,
    workspace_id: str | None = None,
    force_recommit: bool = False,
) -> LedgerRecovery:
    """Append one house ledger commit from the already-booked ``positions`` row.

    Does not call ``book_portfolio``. ``apply=False`` is a read-only dry run.
    When a head commit exists, matching approved weights are ``already_committed``
    (publishing a missing commit-run document only). A mismatch is ``conflict``
    unless ``force_recommit``.
    """
    overlay = workspace_id
    weights, cash_pct, nav = _load_book(client=client, run_date=run_date, workspace_id=overlay)
    if not weights and cash_pct <= 0:
        return _outcome(
            run_date=run_date,
            status="no_book",
            commit_id=None,
            source_run_id=None,
            weights={},
            cash_pct=0.0,
            nav=nav,
            message=f"no positions for {run_date.isoformat()}",
        )

    manifests = load_commit_manifests(client=client, run_date=run_date, workspace_id=overlay)
    latest, next_seq = resolve_prior_commit(manifests)
    prior_commits = _rows_for_date(
        client=client, table=COMMITS, run_date=run_date, workspace_id=overlay
    )
    commit_heads = _heads(prior_commits)
    head_ids = {str(row.get("id")) for row in commit_heads if row.get("id")}
    approved_match = _approved_matches_book(
        client=client,
        run_date=run_date,
        workspace_id=overlay,
        weights=weights,
        cash_pct=cash_pct,
    )
    book_fp = weights_fingerprint(weights)
    latest_id = str((latest or {}).get("ledger_commit_id") or "") or None
    latest_source = str((latest or {}).get("source_run_id") or "") or None

    if latest is None and manifests:
        return _outcome(
            run_date=run_date,
            status="conflict",
            commit_id=latest_id,
            source_run_id=latest_source,
            weights=weights,
            cash_pct=cash_pct,
            nav=nav,
            message=f"ambiguous commit_seq for {run_date.isoformat()}; will not guess the head",
        )

    if not force_recommit:
        if latest is not None and latest.get("status") == "committed":
            manifest_fp = str(latest.get("weights_fingerprint") or "")
            if manifest_fp != book_fp:
                logger.warning(
                    "recover_ledger: fingerprint mismatch for %s (commit=%s)",
                    run_date.isoformat(),
                    latest_id,
                )
                return _outcome(
                    run_date=run_date,
                    status="conflict",
                    commit_id=latest_id,
                    source_run_id=latest_source,
                    weights=weights,
                    cash_pct=cash_pct,
                    nav=nav,
                    message=(
                        f"committed manifest fingerprint does not match booked positions "
                        f"for {run_date.isoformat()}"
                    ),
                )
            if latest_id and latest_id in head_ids and approved_match:
                return _outcome(
                    run_date=run_date,
                    status="already_committed",
                    commit_id=latest_id,
                    source_run_id=latest_source,
                    weights=weights,
                    cash_pct=cash_pct,
                    nav=nav,
                    message=(
                        f"ledger commit {latest_id} already present for {run_date.isoformat()}"
                    ),
                )
        if len(commit_heads) > 1:
            return _outcome(
                run_date=run_date,
                status="conflict",
                commit_id=None,
                source_run_id=None,
                weights=weights,
                cash_pct=cash_pct,
                nav=nav,
                message=(
                    f"forked commit chain for {run_date.isoformat()}; "
                    "will not append without --force-recommit"
                ),
            )
        if commit_heads:
            head_id = str(commit_heads[0].get("id") or "") or None
            if approved_match and head_id:
                source_run_id = latest_source
                if apply:
                    has_head_manifest = any(
                        str(m.get("ledger_commit_id") or "") == head_id for m in manifests
                    )
                    if not has_head_manifest:
                        source_run_id = _publish_missing_manifest(
                            client=client,
                            run_date=run_date,
                            overlay=overlay,
                            head_id=head_id,
                            manifests=manifests,
                            next_seq=next_seq,
                            weights=weights,
                            cash_pct=cash_pct,
                            nav=nav,
                        )
                present = f"ledger commit {head_id} already present for {run_date.isoformat()}"
                return _outcome(
                    run_date=run_date,
                    status="already_committed",
                    commit_id=head_id,
                    source_run_id=source_run_id,
                    weights=weights,
                    cash_pct=cash_pct,
                    nav=nav,
                    message=(
                        f"{present}; published missing commit-run manifest" if apply else present
                    ),
                )
            return _outcome(
                run_date=run_date,
                status="conflict",
                commit_id=head_id,
                source_run_id=latest_source,
                weights=weights,
                cash_pct=cash_pct,
                nav=nav,
                message=(
                    f"head commit exists for {run_date.isoformat()} but approved weights "
                    "do not match the book; pass --force-recommit to append"
                ),
            )

    source_run_id = uuid4()
    state = _recovery_state(
        run_date=run_date,
        source_run_id=source_run_id,
        current_weights=_prior_current_weights(
            client=client, run_date=run_date, workspace_id=overlay
        ),
        workspace_id=overlay,
    )
    if not apply:
        return _outcome(
            run_date=run_date,
            status="dry_run",
            commit_id=None,
            source_run_id=str(source_run_id),
            weights=weights,
            cash_pct=cash_pct,
            nav=nav,
            message=(
                f"would append ledger commit for {run_date.isoformat()} "
                f"from {len(weights)} booked tickers (nav={nav})"
            ),
        )

    appended = append_commit_chain(
        client=client,
        state=state,
        weights=weights,
        cash_pct=cash_pct,
        nav=nav,
    )
    if appended is None:
        return _outcome(
            run_date=run_date,
            status="no_book",
            commit_id=None,
            source_run_id=str(source_run_id),
            weights=weights,
            cash_pct=cash_pct,
            nav=nav,
            message="DIGIQUANT_PORTFOLIO_LEDGER disabled; no commit written",
        )
    ledger = appended

    n_decisions = _decision_log_rows(client=client, run_date=run_date)
    _publish_manifest(
        client=client,
        state=state,
        manifest=_manifest(
            source_run_id=str(source_run_id),
            weights=weights,
            cash_pct=cash_pct,
            nav=nav,
            ledger=ledger,
            decision_log_rows=n_decisions,
            commit_seq=next_seq,
            supersedes=_prior_manifest_fingerprints(manifests),
        ),
    )
    return _outcome(
        run_date=run_date,
        status="committed",
        commit_id=ledger.commit_id,
        source_run_id=str(source_run_id),
        weights=weights,
        cash_pct=cash_pct,
        nav=nav,
        message=f"committed {ledger.commit_id} for {run_date.isoformat()}",
    )
