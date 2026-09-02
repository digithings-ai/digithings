"""Recover a ledger commit from an already-booked positions row (#3330, #3426).

Does not re-size. A matching head is ``already_committed`` (missing commit-run
document only). A mismatch is ``conflict`` unless ``force_recommit``.
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
    ORDER_INTENTS,
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


def _recovery_state(
    *,
    run_date: date,
    source_run_id: UUID,
    current_weights: dict[str, float],
    workspace_id: str | None,
) -> AtlasResearchState:
    prefs: dict[str, object] = dict(portfolio_preferences_static(_PORTFOLIO_JSON))
    prefs["current_weights"] = current_weights
    return AtlasResearchState(
        run_id=source_run_id,
        run_type="delta",
        run_date=run_date,
        config=AtlasConfigBundle(preferences=prefs, workspace_id=workspace_id),
    )


def _new_recovery_state(
    *,
    client: SupabaseClient,
    run_date: date,
    workspace_id: str | None,
) -> tuple[UUID, AtlasResearchState]:
    source_run_id = uuid4()
    return source_run_id, _recovery_state(
        run_date=run_date,
        source_run_id=source_run_id,
        current_weights=_prior_current_weights(
            client=client, run_date=run_date, workspace_id=workspace_id
        ),
        workspace_id=workspace_id,
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
    booked = {k: round(v, 4) for k, v in sorted(weights.items())}
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


def _prior_manifest_fingerprints(manifests: list[dict[str, object]]) -> list[str]:
    return [str(m.get("weights_fingerprint")) for m in manifests if m.get("weights_fingerprint")]


def _write_recovery_manifest(
    *,
    client: SupabaseClient,
    state: AtlasResearchState,
    weights: dict[str, float],
    cash_pct: float,
    nav: float,
    ledger: LedgerAppend,
    commit_seq: int,
    manifests: list[dict[str, object]],
) -> None:
    date_str = state.run_date.isoformat()
    publish_document(
        client=client,
        document_key=f"commit-run/{state.run_id}",
        payload=_manifest(
            source_run_id=str(state.run_id),
            weights=weights,
            cash_pct=cash_pct,
            nav=nav,
            ledger=ledger,
            decision_log_rows=_decision_log_rows(client=client, run_date=state.run_date),
            commit_seq=commit_seq,
            supersedes=_prior_manifest_fingerprints(manifests),
        ),
        doc_type="Commit Run",
        run_type=state.run_type,
        title=f"Commit Run {date_str}",
        date_str=date_str,
        category="portfolio",
        segment="commit_run",
        workspace_id=getattr(state.config, "workspace_id", None),
    )


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
    return all(
        abs(_coerce_pct(row.get("approved_weight"))) <= 1e-9
        for symbol, row in by_symbol.items()
        if symbol not in needed
    )


def _chain_has_order_intents(
    *,
    client: SupabaseClient,
    run_date: date,
    workspace_id: str | None,
    weights: dict[str, float],
) -> bool:
    """Last FK table present, or the book has no tradeable names to order."""
    if not weights:
        return True
    orders = _rows_for_date(
        client=client, table=ORDER_INTENTS, run_date=run_date, workspace_id=workspace_id
    )
    return bool(_heads(orders))


def recover_ledger_from_book(
    *,
    client: SupabaseClient,
    run_date: date,
    apply: bool = False,
    workspace_id: str | None = None,
    force_recommit: bool = False,
) -> LedgerRecovery:
    """Append one ledger commit from the already-booked ``positions`` row."""
    weights, cash_pct, nav = _load_book(client=client, run_date=run_date, workspace_id=workspace_id)
    if not weights and cash_pct <= 0:
        return LedgerRecovery(
            run_date=run_date,
            status="no_book",
            commit_id=None,
            source_run_id=None,
            weights={},
            cash_pct=0.0,
            nav=nav,
            message=f"no positions for {run_date.isoformat()}",
        )

    def outcome(
        status: RecoveryStatus,
        message: str,
        *,
        commit_id: str | None = None,
        source_run_id: str | None = None,
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

    manifests = load_commit_manifests(client=client, run_date=run_date, workspace_id=workspace_id)
    latest, next_seq = resolve_prior_commit(manifests)
    prior_commits = _rows_for_date(
        client=client, table=COMMITS, run_date=run_date, workspace_id=workspace_id
    )
    commit_heads = _heads(prior_commits)
    head_ids = {str(row.get("id")) for row in commit_heads if row.get("id")}
    approved_match = _approved_matches_book(
        client=client,
        run_date=run_date,
        workspace_id=workspace_id,
        weights=weights,
        cash_pct=cash_pct,
    )
    chain_complete = _chain_has_order_intents(
        client=client,
        run_date=run_date,
        workspace_id=workspace_id,
        weights=weights,
    )
    book_fp = weights_fingerprint(weights)
    latest_id = str((latest or {}).get("ledger_commit_id") or "") or None
    latest_source = str((latest or {}).get("source_run_id") or "") or None

    if latest is None and manifests:
        return outcome(
            "conflict",
            f"ambiguous commit_seq for {run_date.isoformat()}; will not guess the head",
            commit_id=latest_id,
            source_run_id=latest_source,
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
                return outcome(
                    "conflict",
                    (
                        "committed manifest fingerprint does not match booked positions "
                        f"for {run_date.isoformat()}"
                    ),
                    commit_id=latest_id,
                    source_run_id=latest_source,
                )
            if latest_id and latest_id in head_ids and approved_match and chain_complete:
                return outcome(
                    "already_committed",
                    f"ledger commit {latest_id} already present for {run_date.isoformat()}",
                    commit_id=latest_id,
                    source_run_id=latest_source,
                )
        if len(commit_heads) > 1:
            return outcome(
                "conflict",
                (
                    f"forked commit chain for {run_date.isoformat()}; "
                    "will not append without --force-recommit"
                ),
            )
        if commit_heads:
            head_id = str(commit_heads[0].get("id") or "") or None
            if approved_match and head_id and chain_complete:
                source_run_id = latest_source
                has_head_manifest = any(
                    str(m.get("ledger_commit_id") or "") == head_id for m in manifests
                )
                if apply and not has_head_manifest:
                    new_id, state = _new_recovery_state(
                        client=client, run_date=run_date, workspace_id=workspace_id
                    )
                    _write_recovery_manifest(
                        client=client,
                        state=state,
                        weights=weights,
                        cash_pct=cash_pct,
                        nav=nav,
                        ledger=LedgerAppend(
                            commit_id=head_id, frozen_symbols=[], unpriced_symbols=[]
                        ),
                        commit_seq=next_seq,
                        manifests=manifests,
                    )
                    source_run_id = str(new_id)
                present = f"ledger commit {head_id} already present for {run_date.isoformat()}"
                return outcome(
                    "already_committed",
                    f"{present}; published missing commit-run manifest" if apply else present,
                    commit_id=head_id,
                    source_run_id=source_run_id,
                )
            if not (approved_match and head_id):
                return outcome(
                    "conflict",
                    (
                        f"head commit exists for {run_date.isoformat()} but approved weights "
                        "do not match the book; pass --force-recommit to append"
                    ),
                    commit_id=head_id,
                    source_run_id=latest_source,
                )

    source_run_id, state = _new_recovery_state(
        client=client, run_date=run_date, workspace_id=workspace_id
    )
    if not apply:
        return outcome(
            "dry_run",
            (
                f"would append ledger commit for {run_date.isoformat()} "
                f"from {len(weights)} booked tickers (nav={nav})"
            ),
            source_run_id=str(source_run_id),
        )

    appended = append_commit_chain(
        client=client,
        state=state,
        weights=weights,
        cash_pct=cash_pct,
        nav=nav,
    )
    if appended is None:
        return outcome(
            "no_book",
            "DIGIQUANT_PORTFOLIO_LEDGER disabled; no commit written",
            source_run_id=str(source_run_id),
        )

    _write_recovery_manifest(
        client=client,
        state=state,
        weights=weights,
        cash_pct=cash_pct,
        nav=nav,
        ledger=appended,
        commit_seq=next_seq,
        manifests=manifests,
    )
    return outcome(
        "committed",
        f"committed {appended.commit_id} for {run_date.isoformat()}",
        commit_id=appended.commit_id,
        source_run_id=str(source_run_id),
    )
