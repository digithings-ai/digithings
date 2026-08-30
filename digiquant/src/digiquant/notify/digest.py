"""Tier-filtered daily digest builder for K5 email (reads same views as Olympus dashboard)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol  # score:allow untyped any — Supabase reader Protocol surface

from digiquant.notify.entitlements import ArtifactClass, PlanTier, can
from digiquant.notify.mailgun import MailgunConfig, unsubscribe_url


class SupabaseReader(Protocol):
    def table(self, name: str) -> Any: ...


@dataclass(frozen=True)
class DigestSection:
    title: str
    body: str
    artifact_class: ArtifactClass


@dataclass(frozen=True)
class DigestContent:
    run_date: str
    workspace_id: str
    workspace_name: str
    tier: PlanTier
    unsubscribe_url: str
    sections: tuple[DigestSection, ...]


def _str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _lines_from_items(items: object, limit: int = 10) -> str:
    if not isinstance(items, list):
        return ""
    out: list[str] = []
    for item in items[:limit]:
        text = _str(item)
        if text:
            out.append(f"- {text}")
    return "\n".join(out)


def _snapshot_research_sections(snapshot: dict[str, Any]) -> list[DigestSection]:
    sections: list[DigestSection] = []
    regime = snapshot.get("regime")
    if isinstance(regime, dict):
        lines = [
            f"**Bias**: {_str(regime.get('bias'))}",
            f"**Label**: {_str(regime.get('label'))}",
            f"**Conviction**: {_str(regime.get('conviction'))}",
        ]
        summary = _str(regime.get("summary"))
        if summary:
            lines.append(summary)
        sections.append(
            DigestSection(
                title="Market Regime",
                body="\n".join(lines),
                artifact_class=ArtifactClass.RESEARCH,
            )
        )

    actionable = _lines_from_items(snapshot.get("actionable_summary") or snapshot.get("actionable"))
    if actionable:
        sections.append(
            DigestSection(
                title="Actionable Summary",
                body=actionable,
                artifact_class=ArtifactClass.RESEARCH,
            )
        )

    risks = _lines_from_items(snapshot.get("risk_radar") or snapshot.get("risks"))
    if risks:
        sections.append(
            DigestSection(
                title="Risk Radar",
                body=risks,
                artifact_class=ArtifactClass.RESEARCH,
            )
        )

    scorecard = snapshot.get("sector_scorecard")
    if isinstance(scorecard, list) and scorecard:
        rows = ["| Sector | ETF | Bias |", "|---|---|---|"]
        for row in scorecard[:12]:
            if not isinstance(row, dict):
                continue
            rows.append(
                f"| {_str(row.get('sector'))} | {_str(row.get('etf'))} | {_str(row.get('bias'))} |"
            )
        sections.append(
            DigestSection(
                title="Sector Scorecard",
                body="\n".join(rows),
                artifact_class=ArtifactClass.RESEARCH,
            )
        )

    narrative = snapshot.get("narrative")
    if isinstance(narrative, dict):
        nar_lines: list[str] = []
        for key in ("alt_data", "institutional", "macro", "us_equities"):
            val = narrative.get(key)
            if val:
                title = key.replace("_", " ").title()
                nar_lines.append(f"### {title}\n{_str(val)}")
        sections.append(
            DigestSection(
                title="Research Narrative",
                body="\n\n".join(nar_lines),
                artifact_class=ArtifactClass.NARRATIVE,
            )
        )

    return sections


def _house_weights_section(positions: list[dict[str, Any]]) -> DigestSection | None:
    if not positions:
        return None
    lines = ["| Ticker | Weight % |", "|---|---|"]
    for row in positions[:25]:
        ticker = _str(row.get("ticker") or row.get("symbol"))
        weight = row.get("weight_pct")
        if ticker and weight is not None:
            lines.append(f"| {ticker} | {weight}% |")
    if len(lines) <= 2:
        return None
    return DigestSection(
        title="House Weights",
        body="\n".join(lines),
        artifact_class=ArtifactClass.HOUSE_WEIGHTS_NAV,
    )


def _nav_section(nav_row: dict[str, Any] | None) -> DigestSection | None:
    if not nav_row:
        return None
    nav = nav_row.get("nav")
    if nav is None:
        return None
    day_ret = nav_row.get("day_return_pct")
    body = f"NAV: {nav}"
    if day_ret is not None:
        body += f"\nDay return: {day_ret}%"
    return DigestSection(
        title="NAV",
        body=body,
        artifact_class=ArtifactClass.HOUSE_WEIGHTS_NAV,
    )


def _glassbox_section(metrics: dict[str, Any] | None) -> DigestSection | None:
    if not metrics:
        return None
    attempts = metrics.get("attempt_count") or metrics.get("attempts")
    spend = metrics.get("research_spend_usd") or metrics.get("spend_usd")
    if attempts is None and spend is None:
        return None
    lines = []
    if attempts is not None:
        lines.append(f"Pipeline attempts: {attempts}")
    if spend is not None:
        lines.append(f"Research spend (USD): {spend}")
    return DigestSection(
        title="Pipeline Economics",
        body="\n".join(lines),
        artifact_class=ArtifactClass.GLASSBOX_ECONOMICS,
    )


def build_digest_content(
    sb: SupabaseReader,
    workspace_id: str,
    tier: PlanTier,
    run_date: date,
    mailgun_config: MailgunConfig,
    workspace_name: str = "Workspace",
) -> DigestContent:
    """Load dashboard-equivalent rows and filter sections by tier entitlements."""
    d = run_date.isoformat()
    raw_sections: list[DigestSection] = []

    snap_res = (
        sb.table("daily_snapshots")
        .select("snapshot,digest_markdown")
        .eq("date", d)
        .limit(1)
        .execute()
    )
    snap_rows = getattr(snap_res, "data", None) or []
    if snap_rows:
        snapshot = snap_rows[0].get("snapshot") or {}
        if isinstance(snapshot, dict):
            raw_sections.extend(_snapshot_research_sections(snapshot))

    pos_res = (
        sb.table("positions")
        .select("ticker,weight_pct")
        .eq("workspace_id", workspace_id)
        .eq("date", d)
        .order("weight_pct", desc=True)
        .limit(30)
        .execute()
    )
    pos_rows = getattr(pos_res, "data", None) or []
    house = _house_weights_section(pos_rows)
    if house:
        raw_sections.append(house)

    nav_res = (
        sb.table("nav_history")
        .select("nav,day_return_pct")
        .eq("workspace_id", workspace_id)
        .eq("date", d)
        .limit(1)
        .execute()
    )
    nav_rows = getattr(nav_res, "data", None) or []
    nav_section = _nav_section(nav_rows[0] if nav_rows else None)
    if nav_section:
        raw_sections.append(nav_section)

    metrics_res = (
        sb.table("portfolio_metrics")
        .select("attempt_count,research_spend_usd")
        .eq("workspace_id", workspace_id)
        .eq("date", d)
        .limit(1)
        .execute()
    )
    metrics_rows = getattr(metrics_res, "data", None) or []
    glass = _glassbox_section(metrics_rows[0] if metrics_rows else None)
    if glass:
        raw_sections.append(glass)

    filtered = tuple(s for s in raw_sections if can(tier, s.artifact_class))
    return DigestContent(
        run_date=d,
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        tier=tier,
        unsubscribe_url=unsubscribe_url(workspace_id, mailgun_config),
        sections=filtered,
    )


__all__ = [
    "DigestContent",
    "DigestSection",
    "build_digest_content",
]
