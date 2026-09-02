"""Inspectable Inputs + bias-row documents for the pipeline graph (WP-B).

Deterministic — no LLM. Reuses :func:`publish_document`. Overlay tenancy is
the workspace stamp on the row; house keys stay unprefixed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any  # score:allow untyped any — JSON-derived prior-context / bias-row slots

from pydantic import BaseModel, ConfigDict, Field

from digiquant.research.state import Phase6BiasRow, ResearchState
from digiquant.research.supabase_io import (
    PublishedArtifact,
    SupabaseClient,
    publish_document,
)

INPUTS_DOCUMENT_KEY = "inputs"
BIAS_ROW_DOCUMENT_KEY = "bias-row"
INPUTS_PAYLOAD_DOC_TYPE = "inputs"
BIAS_ROW_PAYLOAD_DOC_TYPE = "bias_row"
_INSPECTABLE_CATEGORY = "output"


class ProfileIdentity(BaseModel):
    """Hashed profile/preferences identity — never dump raw preference blobs."""

    model_config = ConfigDict(extra="forbid")

    profile_config_version_id: str | None = None
    workspace_id: str | None = None
    preferences_digest: str = ""
    investment_profile_digest: str = ""


class MarketDataFreshness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_technicals_latest: date | None = None
    price_technicals_ticker_count: int = 0
    macro_series_latest: date | None = None
    fallback_used: str = "none"
    stale_price: bool = False
    stale_macro: bool = False
    price_basket_gap: list[str] = Field(default_factory=list)


class PriorContextDates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_snapshot_date: date | None = None
    latest_segment_dates: dict[str, str] = Field(default_factory=dict)
    active_theses_count: int = 0
    prior_book_tickers: list[str] = Field(default_factory=list)


class InputsDocumentPayload(BaseModel):
    """Pydantic envelope for ``document_key=inputs``."""

    model_config = ConfigDict(extra="forbid")

    doc_type: str = INPUTS_PAYLOAD_DOC_TYPE
    date: date
    watchlist: list[str] = Field(default_factory=list)
    profile: ProfileIdentity = Field(default_factory=ProfileIdentity)
    market_data: MarketDataFreshness = Field(default_factory=MarketDataFreshness)
    prior_context: PriorContextDates = Field(default_factory=PriorContextDates)
    attention_plan_key: str | None = None


class BiasRowDocumentPayload(BaseModel):
    """Pydantic envelope for ``document_key=bias-row``."""

    model_config = ConfigDict(extra="forbid")

    doc_type: str = BIAS_ROW_PAYLOAD_DOC_TYPE
    date: date
    run_type: str = ""
    macro_regime: str = ""
    equity_bias: str = ""
    crypto_bias: str = ""
    bond_bias: str = ""
    commodity_bias: str = ""
    forex_bias: str = ""
    vix_level: float | None = None
    inst_flow: str = ""
    options_sentiment: str = ""
    cta_direction: str = ""
    hf_consensus: str = ""
    fed_odds: Any | None = None
    onchain_positioning: Any | None = None
    notes: str = ""


def _stable_digest(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _parse_iso_date(raw: Any) -> date | None:
    if isinstance(raw, date):
        return raw
    text = str(raw or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _coerce_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def build_inputs_payload(
    state: ResearchState,
    *,
    attention_plan_key: str | None = None,
) -> InputsDocumentPayload:
    """Assemble the Inputs document from preflight state (no LLM)."""
    layer = state.data_layer
    prior = state.prior_context
    last_snap = prior.last_snapshots[0] if prior.last_snapshots else None
    last_snap_date = None
    if isinstance(last_snap, dict):
        last_snap_date = _parse_iso_date(last_snap.get("date"))

    segment_dates: dict[str, str] = {}
    for key, row in prior.latest_segments.items():
        if isinstance(row, dict) and row.get("date"):
            parsed = _parse_iso_date(row.get("date"))
            if parsed is not None:
                segment_dates[str(key)] = parsed.isoformat()

    book_tickers: list[str] = []
    for row in prior.prior_book:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker and ticker != "CASH" and ticker not in book_tickers:
            book_tickers.append(ticker)

    return InputsDocumentPayload(
        date=state.run_date,
        watchlist=list(state.config.watchlist),
        profile=ProfileIdentity(
            profile_config_version_id=state.config.profile_config_version_id,
            workspace_id=state.config.workspace_id,
            preferences_digest=_stable_digest(dict(state.config.preferences)),
            investment_profile_digest=_stable_digest(dict(state.config.investment_profile)),
        ),
        market_data=MarketDataFreshness(
            price_technicals_latest=layer.price_technicals_latest,
            price_technicals_ticker_count=layer.price_technicals_ticker_count,
            macro_series_latest=layer.macro_series_latest,
            fallback_used=layer.fallback_used,
            stale_price=layer.stale_price,
            stale_macro=layer.stale_macro,
            price_basket_gap=list(layer.price_basket_gap),
        ),
        prior_context=PriorContextDates(
            last_snapshot_date=last_snap_date,
            latest_segment_dates=segment_dates,
            active_theses_count=len(prior.active_theses),
            prior_book_tickers=book_tickers,
        ),
        attention_plan_key=attention_plan_key,
    )


def render_inputs_markdown(payload: InputsDocumentPayload) -> str:
    """Short readable table — operator artifact, not a JSON dump."""
    md = payload.model_dump(mode="json")
    profile = md["profile"]
    market = md["market_data"]
    prior = md["prior_context"]
    watchlist = ", ".join(md["watchlist"]) or "—"
    lines = [
        f"# Inputs {md['date']}",
        "",
        "| Slot | Value |",
        "| --- | --- |",
        f"| Watchlist | {watchlist} |",
        f"| Profile pin | {profile.get('profile_config_version_id') or '—'} |",
        f"| Preferences digest | {profile.get('preferences_digest') or '—'} |",
        f"| Investment-profile digest | {profile.get('investment_profile_digest') or '—'} |",
        f"| Price technicals latest | {market.get('price_technicals_latest') or '—'} |",
        f"| Macro series latest | {market.get('macro_series_latest') or '—'} |",
        f"| Stale price | {market.get('stale_price')} |",
        f"| Stale macro | {market.get('stale_macro')} |",
        f"| Price basket gap | {', '.join(market.get('price_basket_gap') or []) or '—'} |",
        f"| Last snapshot | {prior.get('last_snapshot_date') or '—'} |",
        f"| Active theses | {prior.get('active_theses_count')} |",
        f"| Attention plan | {md.get('attention_plan_key') or '—'} |",
        "",
    ]
    return "\n".join(lines)


def build_bias_row_payload(row: Phase6BiasRow | dict[str, Any]) -> BiasRowDocumentPayload:
    """Wrap the deterministic phase6 dict in a document envelope."""
    data = dict(row)
    run_date = _parse_iso_date(data.get("date")) or date.min
    return BiasRowDocumentPayload(
        date=run_date,
        run_type=str(data.get("run_type") or ""),
        macro_regime=str(data.get("macro_regime") or ""),
        equity_bias=str(data.get("equity_bias") or ""),
        crypto_bias=str(data.get("crypto_bias") or ""),
        bond_bias=str(data.get("bond_bias") or ""),
        commodity_bias=str(data.get("commodity_bias") or ""),
        forex_bias=str(data.get("forex_bias") or ""),
        vix_level=_coerce_optional_float(data.get("vix_level")),
        inst_flow=str(data.get("inst_flow") or ""),
        options_sentiment=str(data.get("options_sentiment") or ""),
        cta_direction=str(data.get("cta_direction") or ""),
        hf_consensus=str(data.get("hf_consensus") or ""),
        fed_odds=data.get("fed_odds"),
        onchain_positioning=data.get("onchain_positioning"),
        notes=str(data.get("notes") or ""),
    )


def render_bias_row_markdown(payload: BiasRowDocumentPayload) -> str:
    dumped = payload.model_dump(mode="json")
    rows = [
        ("Macro regime", dumped.get("macro_regime")),
        ("Equity", dumped.get("equity_bias")),
        ("Crypto", dumped.get("crypto_bias")),
        ("Bonds", dumped.get("bond_bias")),
        ("Commodities", dumped.get("commodity_bias")),
        ("Forex", dumped.get("forex_bias")),
        ("VIX", dumped.get("vix_level")),
        ("Inst flow", dumped.get("inst_flow")),
        ("Options", dumped.get("options_sentiment")),
        ("CTA", dumped.get("cta_direction")),
        ("HF consensus", dumped.get("hf_consensus")),
    ]
    lines = [
        f"# Bias row {dumped['date']}",
        "",
        "| Slot | Value |",
        "| --- | --- |",
    ]
    for label, value in rows:
        cell = "—" if value in (None, "") else value
        lines.append(f"| {label} | {cell} |")
    notes = str(dumped.get("notes") or "").strip()
    if notes:
        lines.extend(["", "## Notes", "", notes, ""])
    else:
        lines.append("")
    return "\n".join(lines)


def publish_inputs_document(
    *,
    client: SupabaseClient,
    state: ResearchState,
    attention_plan_key: str | None = None,
) -> PublishedArtifact:
    payload = build_inputs_payload(state, attention_plan_key=attention_plan_key)
    date_str = state.run_date.isoformat()
    return publish_document(
        client=client,
        document_key=INPUTS_DOCUMENT_KEY,
        payload=payload.model_dump(mode="json"),
        doc_type=None,
        run_type=state.run_type,
        title=f"Inputs {date_str}",
        date_str=date_str,
        category=_INSPECTABLE_CATEGORY,
        segment="inputs",
        content_markdown=render_inputs_markdown(payload),
        workspace_id=getattr(state.config, "workspace_id", None),
    )


def publish_bias_row_document(
    *,
    client: SupabaseClient,
    state: ResearchState,
) -> PublishedArtifact | None:
    row = state.phase6_bias_row
    if not row:
        return None
    payload = build_bias_row_payload(row)
    date_str = state.run_date.isoformat()
    return publish_document(
        client=client,
        document_key=BIAS_ROW_DOCUMENT_KEY,
        payload=payload.model_dump(mode="json"),
        doc_type=None,
        run_type=state.run_type,
        title=f"Bias row {date_str}",
        date_str=date_str,
        category=_INSPECTABLE_CATEGORY,
        segment="bias-row",
        content_markdown=render_bias_row_markdown(payload),
        workspace_id=getattr(state.config, "workspace_id", None),
    )


__all__ = [
    "BIAS_ROW_DOCUMENT_KEY",
    "BIAS_ROW_PAYLOAD_DOC_TYPE",
    "BiasRowDocumentPayload",
    "INPUTS_DOCUMENT_KEY",
    "INPUTS_PAYLOAD_DOC_TYPE",
    "InputsDocumentPayload",
    "build_bias_row_payload",
    "build_inputs_payload",
    "publish_bias_row_document",
    "publish_inputs_document",
    "render_bias_row_markdown",
    "render_inputs_markdown",
]
