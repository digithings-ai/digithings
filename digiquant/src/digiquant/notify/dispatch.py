"""K5 notification dispatch — cron entry and daily-run hook (fail-soft)."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol  # score:allow untyped any — Supabase / Jinja render Protocol surface

from jinja2 import Environment, FileSystemLoader, select_autoescape

from digiquant.data.store.client import build_digiquant_client
from digiquant.notify.digest import DigestContent, build_digest_content
from digiquant.notify.entitlements import PlanTier, is_plan_tier
from digiquant.notify.events import (
    ExecutionAlertEvent,
    HoldingChangeEvent,
    detect_execution_alerts,
    detect_holding_changes,
)
from digiquant.notify.mailgun import (
    MailgunClientProtocol,
    MailgunConfig,
    MailgunTransportError,
    build_mailgun_client,
)

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class SupabaseReader(Protocol):
    def table(self, name: str) -> Any: ...


@lru_cache(maxsize=1)
def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
    )


def _render_daily_digest(content: DigestContent) -> tuple[str, str]:
    ctx = {
        "run_date": content.run_date,
        "workspace_name": content.workspace_name,
        "tier": content.tier.value,
        "unsubscribe_url": content.unsubscribe_url,
        "sections": [
            {"title": s.title, "body": s.body, "artifact_class": s.artifact_class.value}
            for s in content.sections
        ],
    }
    env = _jinja_env()
    return (
        env.get_template("daily_digest.txt.j2").render(**ctx),
        env.get_template("daily_digest.html.j2").render(**ctx),
    )


def _render_holding_change(event: HoldingChangeEvent) -> tuple[str, str]:
    ctx = {
        "run_date": event.run_date,
        "ticker": event.ticker,
        "change_kind": event.change_kind,
        "current_weight_pct": event.current_weight_pct,
        "prior_weight_pct": event.prior_weight_pct,
        "delta_pp": event.delta_pp,
        "unsubscribe_url": event.unsubscribe_url,
    }
    env = _jinja_env()
    return (
        env.get_template("holding_change.txt.j2").render(**ctx),
        env.get_template("holding_change.html.j2").render(**ctx),
    )


def _render_execution_alert(event: ExecutionAlertEvent) -> tuple[str, str]:
    ctx = {
        "run_date": event.run_date,
        "symbol": event.symbol,
        "side": event.side,
        "quantity": event.quantity,
        "price": event.price,
        "executed_at": event.executed_at,
        "unsubscribe_url": event.unsubscribe_url,
    }
    env = _jinja_env()
    return (
        env.get_template("execution_alert.txt.j2").render(**ctx),
        env.get_template("execution_alert.html.j2").render(**ctx),
    )


def try_claim_send_slot(
    sb: SupabaseReader,
    workspace_id: str,
    event_key: str,
    sent_date: date,
) -> bool:
    """Insert-first dedupe — False when already sent today."""
    try:
        sb.table("notification_log").insert(
            {
                "workspace_id": workspace_id,
                "event_key": event_key,
                "sent_date": sent_date.isoformat(),
            }
        ).execute()
        return True
    except Exception as exc:
        err = str(exc).lower()
        if "duplicate" in err or "23505" in err or "unique" in err:
            return False
        raise


def _load_prefs(sb: SupabaseReader) -> list[dict[str, Any]]:
    res = sb.table("notification_prefs").select("*").execute()
    return list(getattr(res, "data", None) or [])


def _workspace_tier(sb: SupabaseReader, workspace_id: str) -> PlanTier:
    res = sb.table("workspaces").select("plan_tier,name").eq("id", workspace_id).limit(1).execute()
    rows = getattr(res, "data", None) or []
    if not rows:
        return PlanTier.FREE
    raw = rows[0].get("plan_tier")
    if is_plan_tier(raw):
        return PlanTier(raw)
    return PlanTier.FREE


def _workspace_name(sb: SupabaseReader, workspace_id: str) -> str:
    res = sb.table("workspaces").select("name,slug").eq("id", workspace_id).limit(1).execute()
    rows = getattr(res, "data", None) or []
    if not rows:
        return "Workspace"
    name = rows[0].get("name") or rows[0].get("slug")
    return str(name or "Workspace")


def _send_if_allowed(
    client: MailgunClientProtocol,
    email: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> bool:
    if client.is_suppressed(email):
        logger.warning(
            "notify: suppressed address skipped", extra={"email_domain": email.split("@")[-1]}
        )
        return False
    client.send_message(to=email, subject=subject, text_body=text_body, html_body=html_body)
    return True


def dispatch_workspace(
    sb: SupabaseReader,
    client: MailgunClientProtocol,
    mailgun_config: MailgunConfig,
    pref: dict[str, Any],
    run_date: date,
    hour_utc: int | None,
) -> None:
    workspace_id = str(pref["workspace_id"])
    email = str(pref.get("email") or "").strip()
    if not email:
        return

    tier = _workspace_tier(sb, workspace_id)
    workspace_name = _workspace_name(sb, workspace_id)
    digest_hour = int(pref.get("digest_hour_utc") or 12)

    if pref.get("daily_digest"):
        if hour_utc is None or hour_utc == digest_hour:
            event_key = f"digest:{run_date.isoformat()}"
            if try_claim_send_slot(sb, workspace_id, event_key, run_date):
                content = build_digest_content(
                    sb,
                    workspace_id,
                    tier,
                    run_date,
                    mailgun_config,
                    workspace_name=workspace_name,
                )
                text, html = _render_daily_digest(content)
                subject = f"Olympus daily digest — {run_date.isoformat()}"
                try:
                    _send_if_allowed(client, email, subject, text, html)
                except MailgunTransportError as exc:
                    logger.warning("notify: digest send failed: %s", exc)

    if pref.get("holding_change_alerts"):
        for event in detect_holding_changes(sb, workspace_id, run_date, mailgun_config):
            if not try_claim_send_slot(sb, workspace_id, event.event_key, run_date):
                continue
            text, html = _render_holding_change(event)
            subject = f"Holding change — {event.ticker} ({run_date.isoformat()})"
            try:
                _send_if_allowed(client, email, subject, text, html)
            except MailgunTransportError as exc:
                logger.warning("notify: holding-change send failed: %s", exc)

    if pref.get("execution_alerts"):
        for event in detect_execution_alerts(sb, workspace_id, run_date, mailgun_config):
            if not try_claim_send_slot(sb, workspace_id, event.event_key, run_date):
                continue
            text, html = _render_execution_alert(event)
            subject = f"Execution alert — {event.symbol} ({run_date.isoformat()})"
            try:
                _send_if_allowed(client, email, subject, text, html)
            except MailgunTransportError as exc:
                logger.warning("notify: execution alert send failed: %s", exc)


def dispatch_notifications(
    run_date: date | None = None,
    hour_utc: int | None = None,
) -> None:
    """Dispatch all notification types for workspaces with prefs (fail-soft — never raises)."""
    try:
        _dispatch_notifications_inner(run_date, hour_utc)
    except Exception:
        logger.warning("notify: dispatch failed", exc_info=True)


def _dispatch_notifications_inner(
    run_date: date | None = None,
    hour_utc: int | None = None,
) -> None:
    sb = build_digiquant_client()
    if sb is None:
        logger.warning("notify: supabase credentials missing — skip dispatch")
        return
    mailgun_config = MailgunConfig.from_env()
    if mailgun_config is None:
        logger.warning("notify: mailgun env incomplete — skip dispatch")
        return
    client = build_mailgun_client()
    if client is None:
        logger.warning("notify: mailgun client unavailable — skip dispatch")
        return

    effective_date = run_date or datetime.now(UTC).date()
    effective_hour = hour_utc if hour_utc is not None else datetime.now(UTC).hour

    prefs = _load_prefs(sb)
    for pref in prefs:
        try:
            dispatch_workspace(
                sb,
                client,
                mailgun_config,
                pref,
                effective_date,
                effective_hour,
            )
        except Exception:
            logger.warning(
                "notify: workspace dispatch failed",
                extra={"workspace_id": pref.get("workspace_id")},
                exc_info=True,
            )


def main() -> None:
    """CLI entry: ``python -m digiquant.notify.dispatch``."""
    logging.basicConfig(level=logging.INFO)
    dispatch_notifications()


if __name__ == "__main__":
    main()
