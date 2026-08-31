"""Recover an H9 ledger commit from an already-booked positions row (#3330).

Use when ``book_portfolio`` wrote ``positions`` / ``nav_history`` but
``append_commit_chain`` died before the insert (e.g. ``23502`` missing
``workspace_id`` on main). Reads the decided book; does not re-size or call an LLM.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID, uuid4

from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState
from digiquant.olympus.atlas.supabase_io import (
    SupabaseClient,
    SupabaseConfig,
    build_client,
    load_prior_book,
    publish_document,
)
from digiquant.olympus.hermes.writers.commit_io import (
    load_commit_manifests,
    weights_fingerprint,
)
from digiquant.olympus.hermes.writers.ledger_io import (
    COMMITS,
    LedgerAppend,
    _rows_for_date,
    append_commit_chain,
)
from digiquant.olympus.tenancy import house_workspace_id, resolved_workspace_id

logger = logging.getLogger(__name__)

_CASH = "CASH"
RecoveryStatus = Literal["dry_run", "committed", "already_committed", "no_book"]


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


def _symbol(raw: object) -> str:
    return str(raw or "").strip().upper()


def _load_book(
    *, client: SupabaseClient, run_date: date, workspace_id: str | None
) -> tuple[dict[str, float], float, float]:
    """Non-cash weights (percent), cash_pct, nav from the already-booked day."""
    date_str = run_date.isoformat()
    scoped = str(resolved_workspace_id(workspace_id))
    pos_resp = (
        client.table("positions")
        .select("ticker, weight_pct")
        .eq("date", date_str)
        .eq("workspace_id", scoped)
        .execute()
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
    nav_resp = (
        client.table("nav_history")
        .select("nav, cash_pct")
        .eq("date", date_str)
        .eq("workspace_id", scoped)
        .execute()
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
    out: dict[str, float] = {}
    for row in prior:
        ticker = _symbol(row.get("ticker"))
        if ticker:
            out[ticker] = _coerce_pct(row.get("weight_pct"))
    return out


def _decision_log_rows(*, client: SupabaseClient, run_date: date) -> int:
    resp = (
        client.table("decision_log").select("ticker").eq("run_date", run_date.isoformat()).execute()
    )
    return len(list(resp.data or []))


def _recovery_state(
    *,
    run_date: date,
    source_run_id: UUID,
    current_weights: dict[str, float],
    workspace_id: str | None,
) -> AtlasResearchState:
    prefs: dict[str, object] = {"current_weights": current_weights}
    return AtlasResearchState(
        run_id=source_run_id,
        run_type="delta",
        run_date=run_date,
        config=AtlasConfigBundle(preferences=prefs, workspace_id=workspace_id),
    )


def _manifest(
    *,
    source_run_id: str,
    weights: dict[str, float],
    cash_pct: float,
    nav: float,
    ledger: LedgerAppend,
    decision_log_rows: int,
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
        "commit_seq": 1,
        "supersedes": [],
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


def recover_ledger_from_book(
    *,
    client: SupabaseClient,
    run_date: date,
    apply: bool = False,
    workspace_id: str | None = None,
) -> LedgerRecovery:
    """Append one house ledger commit from the already-booked ``positions`` row.

    Does not call ``book_portfolio`` or H8. ``apply=False`` is a read-only dry run.
    """
    overlay = workspace_id
    weights, cash_pct, nav = _load_book(client=client, run_date=run_date, workspace_id=overlay)
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

    manifests = load_commit_manifests(client=client, run_date=run_date, workspace_id=overlay)
    committed_manifests = [m for m in manifests if m.get("status") == "committed"]
    prior_commits = _rows_for_date(
        client=client, table=COMMITS, run_date=run_date, workspace_id=overlay
    )
    existing_id = None
    if committed_manifests:
        existing_id = str(committed_manifests[0].get("ledger_commit_id") or "") or None
    if existing_id is None and prior_commits:
        existing_id = str(prior_commits[0].get("id") or "") or None

    if existing_id and committed_manifests:
        return LedgerRecovery(
            run_date=run_date,
            status="already_committed",
            commit_id=existing_id,
            source_run_id=str(committed_manifests[0].get("source_run_id") or "") or None,
            weights=weights,
            cash_pct=cash_pct,
            nav=nav,
            message=f"ledger commit {existing_id} already present for {run_date.isoformat()}",
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
        return LedgerRecovery(
            run_date=run_date,
            status="dry_run",
            commit_id=existing_id,
            source_run_id=str(source_run_id),
            weights=weights,
            cash_pct=cash_pct,
            nav=nav,
            message=(
                f"would append ledger commit for {run_date.isoformat()} "
                f"from {len(weights)} booked tickers (nav={nav})"
            ),
        )

    if existing_id:
        ledger = LedgerAppend(commit_id=existing_id, frozen_symbols=[], unpriced_symbols=[])
    else:
        appended = append_commit_chain(
            client=client,
            state=state,
            weights=weights,
            cash_pct=cash_pct,
            nav=nav,
        )
        if appended is None:
            return LedgerRecovery(
                run_date=run_date,
                status="no_book",
                commit_id=None,
                source_run_id=str(source_run_id),
                weights=weights,
                cash_pct=cash_pct,
                nav=nav,
                message="OLYMPUS_PORTFOLIO_LEDGER disabled; no commit written",
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
        ),
    )
    status: RecoveryStatus = "already_committed" if existing_id and prior_commits else "committed"
    return LedgerRecovery(
        run_date=run_date,
        status=status,
        commit_id=ledger.commit_id,
        source_run_id=str(source_run_id),
        weights=weights,
        cash_pct=cash_pct,
        nav=nav,
        message=f"committed {ledger.commit_id} for {run_date.isoformat()}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Append H9 ledger commit from existing positions (no LLM)."
    )
    parser.add_argument("--date", required=True, help="Run date YYYY-MM-DD")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the ledger + commit-run document. Default is dry-run.",
    )
    args = parser.parse_args(argv)
    run_date = date.fromisoformat(args.date)

    client = build_client(SupabaseConfig.from_env())
    result = recover_ledger_from_book(client=client, run_date=run_date, apply=args.apply)
    payload = {
        "run_date": result.run_date.isoformat(),
        "status": result.status,
        "commit_id": result.commit_id,
        "source_run_id": result.source_run_id,
        "weights": result.weights,
        "cash_pct": result.cash_pct,
        "nav": result.nav,
        "message": result.message,
        "house_workspace_id": str(house_workspace_id()),
        "apply": args.apply,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if result.status == "no_book":
        return 2
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
