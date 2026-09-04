"""K5 notification dispatch — cron entry and daily-run hook (fail-soft)."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import (  # score:allow untyped any — Supabase / Jinja render Protocol surface
    Any,
    Protocol,
)

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, ConfigDict

from digiquant.data.store.client import build_digiquant_client
from digiquant.notify.digest import DigestContent, build_digest_content
from digiquant.notify.entitlements import ArtifactClass, PlanTier, can, is_plan_tier
from digiquant.notify.events import (
    ExecutionAlertEvent,
    HoldingChangeEvent,
    detect_execution_alerts,
    detect_holding_changes,
)
from digiquant.notify.mailgun import (
    MailgunClientProtocol,
    MailgunConfig,
    MailgunNotConfiguredError,
    MailgunTransportError,
    build_mailgun_client,
    format_mailgun_not_configured,
    missing_mailgun_env_names,
)

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
NOTIFY_STORE_NOT_CONFIGURED = "NOTIFY_STORE_NOT_CONFIGURED"


class SupabaseReader(Protocol):
    def table(self, name: str) -> Any: ...


class DigestDryRunPlan(BaseModel):
    """Sanitized digest dispatch preview — counts only, no emails."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    considered: int
    digest_on: int
    skipped_prefs_off: int
    skipped_no_email: int
    mailgun_configured: bool


def plan_digest_dispatch(
    prefs: Sequence[Mapping[str, Any]],
    *,
    mailgun_configured: bool,
    workspace_id: str | None = None,
) -> DigestDryRunPlan:
    """Classify prefs the same way ``dispatch_workspace`` gates digest send."""
    rows = list(prefs)
    if workspace_id:
        rows = [pref for pref in rows if str(pref.get("workspace_id") or "") == workspace_id]
    digest_on = 0
    skipped_prefs_off = 0
    skipped_no_email = 0
    for pref in rows:
        email = str(pref.get("email") or "").strip()
        if not email:
            skipped_no_email += 1
            continue
        if not pref.get("daily_digest"):
            skipped_prefs_off += 1
            continue
        digest_on += 1
    return DigestDryRunPlan(
        considered=len(rows),
        digest_on=digest_on,
        skipped_prefs_off=skipped_prefs_off,
        skipped_no_email=skipped_no_email,
        mailgun_configured=mailgun_configured,
    )


def format_digest_dry_run(plan: DigestDryRunPlan) -> str:
    return (
        f"notify dry-run considered={plan.considered} digest_on={plan.digest_on} "
        f"skipped_prefs_off={plan.skipped_prefs_off} skipped_no_email={plan.skipped_no_email} "
        f"mailgun_configured={int(plan.mailgun_configured)}"
    )


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


def _is_suppressed(client: MailgunClientProtocol, email: str) -> bool:
    if client.is_suppressed(email):
        logger.warning(
            "notify: suppressed address skipped", extra={"email_domain": email.split("@")[-1]}
        )
        return True
    return False


def _send_message(
    client: MailgunClientProtocol,
    email: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> None:
    client.send_message(to=email, subject=subject, text_body=text_body, html_body=html_body)


def dispatch_workspace(
    sb: SupabaseReader,
    client: MailgunClientProtocol,
    mailgun_config: MailgunConfig,
    pref: dict[str, Any],
    run_date: date,
    hour_utc: int,
    *,
    force_digest: bool = False,
    execution_alerts_only: bool = False,
) -> None:
    workspace_id = str(pref["workspace_id"])
    email = str(pref.get("email") or "").strip()
    if not email:
        return

    tier = _workspace_tier(sb, workspace_id)
    workspace_name = _workspace_name(sb, workspace_id)
    digest_hour = int(pref.get("digest_hour_utc") or 12)

    if not execution_alerts_only and pref.get("daily_digest"):
        if force_digest or hour_utc == digest_hour:
            if not _is_suppressed(client, email):
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
                    subject = f"dashboard daily digest — {run_date.isoformat()}"
                    try:
                        _send_message(client, email, subject, text, html)
                    except MailgunTransportError as exc:
                        logger.warning("notify: digest send failed: %s", exc)

    if not execution_alerts_only and pref.get("holding_change_alerts"):
        if can(tier, ArtifactClass.HOUSE_WEIGHTS_NAV):
            for event in detect_holding_changes(sb, workspace_id, run_date, mailgun_config):
                if _is_suppressed(client, email):
                    break
                if not try_claim_send_slot(sb, workspace_id, event.event_key, run_date):
                    continue
                text, html = _render_holding_change(event)
                subject = f"Holding change — {event.ticker} ({run_date.isoformat()})"
                try:
                    _send_message(client, email, subject, text, html)
                except MailgunTransportError as exc:
                    logger.warning("notify: holding-change send failed: %s", exc)

    if pref.get("execution_alerts") and can(tier, ArtifactClass.BROKER_STATUS):
        for event in detect_execution_alerts(sb, workspace_id, run_date, mailgun_config):
            if _is_suppressed(client, email):
                break
            if not try_claim_send_slot(sb, workspace_id, event.event_key, run_date):
                continue
            text, html = _render_execution_alert(event)
            subject = f"Execution alert — {event.symbol} ({run_date.isoformat()})"
            try:
                _send_message(client, email, subject, text, html)
            except MailgunTransportError as exc:
                logger.warning("notify: execution alert send failed: %s", exc)


def _dispatch_with_client(
    sb: SupabaseReader,
    client: MailgunClientProtocol,
    mailgun_config: MailgunConfig,
    run_date: date,
    hour_utc: int,
    *,
    force_digest: bool = False,
    execution_alerts_only: bool = False,
) -> None:
    prefs = _load_prefs(sb)
    for pref in prefs:
        try:
            dispatch_workspace(
                sb,
                client,
                mailgun_config,
                pref,
                run_date,
                hour_utc,
                force_digest=force_digest,
                execution_alerts_only=execution_alerts_only,
            )
        except Exception:
            logger.warning(
                "notify: workspace dispatch failed",
                extra={"workspace_id": pref.get("workspace_id")},
                exc_info=True,
            )


def dispatch_notifications(
    run_date: date | None = None,
    hour_utc: int | None = None,
    *,
    force_digest: bool = False,
) -> None:
    """Dispatch digest + holding-change + execution alerts (fail-soft — never raises).

    **Cron** (`python -m digiquant.notify.dispatch`): passes ``hour_utc=now.hour`` so
    daily digests respect ``notification_prefs.digest_hour_utc``.

    **Post-run** (`run_db_first.py` close-out and house ``portfolio.chain`` CLI):
    passes ``force_digest=True`` so today's digest always attempts send regardless
    of hour; dedupe prevents double-send if cron already delivered. Overlay
    nested ``run_research_then_portfolio`` does not call this.
    """
    try:
        _dispatch_notifications_inner(
            run_date,
            hour_utc,
            force_digest=force_digest,
            execution_alerts_only=False,
        )
    except Exception:
        logger.warning("notify: dispatch failed", exc_info=True)


def dispatch_execution_alerts(run_date: date | None = None) -> None:
    """Execution-alert-only dispatch for K4 sync tail (fail-soft — never raises)."""
    try:
        _dispatch_notifications_inner(
            run_date,
            hour_utc=datetime.now(UTC).hour,
            force_digest=False,
            execution_alerts_only=True,
        )
    except Exception:
        logger.warning("notify: execution-alert dispatch failed", exc_info=True)


def _dispatch_notifications_inner(
    run_date: date | None = None,
    hour_utc: int | None = None,
    *,
    force_digest: bool = False,
    execution_alerts_only: bool = False,
) -> None:
    sb = build_digiquant_client()
    if sb is None:
        logger.warning("notify: supabase credentials missing — skip dispatch")
        return
    missing = missing_mailgun_env_names()
    if missing:
        # Named code in logs so ops/agents never confuse silent skip with success.
        logger.warning(
            "notify: %s — skip dispatch (fail-soft for cron/post-run)",
            format_mailgun_not_configured(missing),
        )
        return
    mailgun_config = MailgunConfig.from_env()
    if mailgun_config is None:
        logger.warning(
            "notify: %s — skip dispatch",
            format_mailgun_not_configured(list(missing_mailgun_env_names())),
        )
        return
    client = build_mailgun_client()
    if client is None:
        logger.warning(
            "notify: %s — client unavailable, skip dispatch",
            format_mailgun_not_configured(list(missing_mailgun_env_names())),
        )
        return

    effective_date = run_date or datetime.now(UTC).date()
    effective_hour = hour_utc if hour_utc is not None else datetime.now(UTC).hour

    _dispatch_with_client(
        sb,
        client,
        mailgun_config,
        effective_date,
        effective_hour,
        force_digest=force_digest,
        execution_alerts_only=execution_alerts_only,
    )


def _run_digest_dry_run(
    *,
    workspace_id: str | None,
    prefs: Sequence[Mapping[str, Any]] | None,
    mailgun_configured: bool | None,
    log: Callable[[str], None] | None,
) -> int:
    """Print digest candidate counts. Never sends or claims slots."""
    out = log or print
    configured = (
        not bool(missing_mailgun_env_names()) if mailgun_configured is None else mailgun_configured
    )
    loaded: Sequence[Mapping[str, Any]]
    if prefs is None:
        sb = build_digiquant_client()
        if sb is None:
            print(NOTIFY_STORE_NOT_CONFIGURED, file=sys.stderr)
            return 2
        loaded = _load_prefs(sb)
    else:
        loaded = prefs
    plan = plan_digest_dispatch(
        loaded,
        mailgun_configured=configured,
        workspace_id=workspace_id,
    )
    out(format_digest_dry_run(plan))
    return 0


def main(
    argv: list[str] | None = None,
    *,
    prefs: Sequence[Mapping[str, Any]] | None = None,
    mailgun_configured: bool | None = None,
    log: Callable[[str], None] | None = None,
) -> int:
    """CLI entry: ``python -m digiquant.notify.dispatch``.

    Default (cron): hour-gated dispatch; Mailgun gaps are fail-soft inside
    :func:`dispatch_notifications`.

    ``--require-mailgun`` / ``--check``: loud-fail with exit **2** and code
    ``MAILGUN_NOT_CONFIGURED`` listing missing env *names* (no values). Use for
    staging probes and agent gates — never silent green when vendor keys empty.

    ``--dry-run``: load prefs and print candidate counts (no send, no
    ``notification_log`` claim). Mailgun absence is reported as
    ``mailgun_configured=0`` rather than skipping the count. ``--workspace-id``
    filters the plan. Missing store env exits **2** with
    ``NOTIFY_STORE_NOT_CONFIGURED``.
    """
    parser = argparse.ArgumentParser(prog="digiquant.notify.dispatch")
    parser.add_argument(
        "--require-mailgun",
        "--check",
        dest="require_mailgun",
        action="store_true",
        help="Exit 2 with MAILGUN_NOT_CONFIGURED when Mailgun env incomplete",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest candidate counts; do not send or claim slots",
    )
    parser.add_argument(
        "--workspace-id",
        default=None,
        help="Limit --dry-run to one workspace id",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    if args.require_mailgun:
        missing = missing_mailgun_env_names()
        if missing:
            print(format_mailgun_not_configured(missing), file=sys.stderr)
            return 2
        try:
            MailgunConfig.require_from_env()
        except MailgunNotConfiguredError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print("notify: Mailgun env present (names only check; send not attempted)")
        return 0

    if args.dry_run:
        return _run_digest_dry_run(
            workspace_id=args.workspace_id,
            prefs=prefs,
            mailgun_configured=mailgun_configured,
            log=log,
        )

    dispatch_notifications(hour_utc=datetime.now(UTC).hour)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
