"""Overlay daily cron — dispatch ``job_runs`` for non-house workspaces (T4).

Production entry: ``python -m digiquant.dashboard.overlay``. House and system
workspaces are never overlay targets. This module does not import ``byok`` /
digillm so the digiquant-only CI lane can unit-test candidate selection.
``--execute`` runs claimed jobs through the one dashboard graph (lazy import);
``chain=None`` is refused.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from digiquant.dashboard.overlay.cron_execute import (
    OverlayChainFactory,
    OverlayRunner,
    execute_claimed_rows,
    format_overlay_execute_not_configured,
    missing_overlay_execute_env_names,
)
from digiquant.dashboard.overlay.dispatch import (
    DispatchResult,
    JobRunStore,
    SupabaseJobRunStore,
    WorkspaceEntitlement,
    dispatch_overlay_daily,
    overlay_billing_entitled,
)
from digiquant.dashboard.overlay.persist import overlay_persist_enabled
from digiquant.dashboard.tenancy import (
    PlanTier,
    SubscriptionStatus,
    house_workspace_id,
    system_workspace_id,
)


class OverlayByokProbe(Protocol):
    """Duck-typed BYOK probe — production lets dispatch lazy-import ``probe_byok``."""

    present_and_unsealable: bool


class OverlayCronRow(BaseModel):
    """One dispatch outcome for the cron log (ids only, no secrets)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID
    claimed: bool
    status: str
    skip_reason: str | None = None


class OverlayCronReport(BaseModel):
    """Sanitized cron summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_date: date
    considered: int
    dispatched: int
    claimed: int
    skipped: int
    rows: tuple[OverlayCronRow, ...] = Field(default_factory=tuple)


def reserved_overlay_workspace_ids() -> frozenset[UUID]:
    return frozenset({house_workspace_id(), system_workspace_id()})


def parse_workspace_row(row: dict[str, object]) -> WorkspaceEntitlement | None:
    """Build an entitlement from a ``workspaces`` select. Invalid rows skipped."""
    raw_id = row.get("id")
    raw_tier = row.get("plan_tier")
    raw_status = row.get("subscription_status")
    if raw_id is None or not isinstance(raw_tier, str) or not isinstance(raw_status, str):
        return None
    raw_floor = row.get("plan_floor")
    plan_floor: PlanTier | None = None
    if isinstance(raw_floor, str) and raw_floor:
        try:
            plan_floor = PlanTier(raw_floor)
        except ValueError:
            plan_floor = None
    try:
        return WorkspaceEntitlement(
            workspace_id=UUID(str(raw_id)),
            plan_tier=PlanTier(raw_tier),
            subscription_status=SubscriptionStatus(raw_status),
            plan_floor=plan_floor,
        )
    except (ValueError, TypeError):
        return None


def overlay_cron_targets(
    workspaces: Sequence[WorkspaceEntitlement],
) -> tuple[WorkspaceEntitlement, ...]:
    """Exclude house/system. Dispatch still entitlement-gates each remaining row."""
    reserved = reserved_overlay_workspace_ids()
    return tuple(ws for ws in workspaces if ws.workspace_id not in reserved)


def missing_overlay_cron_env_names(environ: Mapping[str, str] | None = None) -> list[str]:
    """Return required *names* that are empty. Never returns values."""
    env = os.environ if environ is None else environ
    aliases = {
        "SUPABASE_URL": ("SUPABASE_URL", "CORE_SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": (
            "SUPABASE_SERVICE_ROLE_KEY",
            "CORE_SUPABASE_SERVICE_KEY",
        ),
    }
    missing: list[str] = []
    for canonical, names in aliases.items():
        if not any((env.get(name) or "").strip() for name in names):
            missing.append(canonical)
    return missing


def format_overlay_store_not_configured(missing: Sequence[str]) -> str:
    return "OVERLAY_STORE_NOT_CONFIGURED: " + ", ".join(missing)


def _select_rows(
    client: object, table: str, columns: str, eq: tuple[str, str] | None = None
) -> list[object]:
    handle = client.table(table)
    query = handle.select(columns)
    if eq is not None:
        query = query.eq(eq[0], eq[1])
    result = query.execute()
    data = getattr(result, "data", result)
    return data if isinstance(data, list) else []


def _auth_emails_by_user_id(client: object) -> dict[str, str]:
    auth = getattr(client, "auth", None)
    admin = getattr(auth, "admin", None) if auth is not None else None
    list_users = getattr(admin, "list_users", None) if admin is not None else None
    if not callable(list_users):
        return {}
    try:
        raw = list_users()
    except Exception:
        # Auth admin is optional; Stripe-only entitlement still applies.
        return {}
    users = getattr(raw, "users", raw)
    if not isinstance(users, list):
        return {}
    out: dict[str, str] = {}
    for user in users:
        uid: object
        email: object
        if isinstance(user, dict):
            uid = user.get("id")
            email = user.get("email")
        else:
            uid = getattr(user, "id", None)
            email = getattr(user, "email", None)
        if uid is None or not isinstance(email, str) or not email.strip():
            continue
        out[str(uid)] = email.strip().lower()
    return out


def load_active_byok_workspace_ids(client: object) -> set[UUID]:
    """Active ``workspace_provider_credentials`` workspace ids (presence only).

    Does not unseal. Missing table or client errors are an empty set so dry-run
    still prints ``byok_present=0`` instead of aborting.
    """
    try:
        raw = _select_rows(
            client,
            "workspace_provider_credentials",
            "workspace_id,status",
            eq=("status", "active"),
        )
    except Exception:
        return set()
    out: set[UUID] = set()
    for row in raw:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip().lower() != "active":
            continue
        try:
            out.add(UUID(str(row["workspace_id"])))
        except (ValueError, TypeError, KeyError):
            continue
    return out


def load_workspace_plan_floors(client: object) -> dict[UUID, PlanTier]:
    """Owner ``entitlement_grants.plan_floor`` keyed by workspace id.

    Missing grant tables, members, or Auth admin are treated as no floors
    (Stripe-only entitlement), not as a hard failure.
    """
    try:
        grants_raw = _select_rows(client, "entitlement_grants", "email,plan_floor")
        members_raw = _select_rows(
            client, "workspace_members", "workspace_id,user_id,role", eq=("role", "owner")
        )
    except (AttributeError, TypeError):
        return {}
    grant_by_email: dict[str, PlanTier] = {}
    for row in grants_raw:
        if not isinstance(row, dict):
            continue
        email = row.get("email")
        raw_floor = row.get("plan_floor")
        if not isinstance(email, str) or not isinstance(raw_floor, str):
            continue
        try:
            grant_by_email[email.strip().lower()] = PlanTier(raw_floor)
        except ValueError:
            continue
    if not grant_by_email:
        return {}
    emails = _auth_emails_by_user_id(client)
    if not emails:
        return {}
    floors: dict[UUID, PlanTier] = {}
    for row in members_raw:
        if not isinstance(row, dict):
            continue
        email = emails.get(str(row.get("user_id") or ""))
        if email is None:
            continue
        floor = grant_by_email.get(email)
        if floor is None:
            continue
        try:
            floors[UUID(str(row["workspace_id"]))] = floor
        except (ValueError, TypeError, KeyError):
            continue
    return floors


def load_overlay_cron_workspaces(client: object) -> list[WorkspaceEntitlement]:
    """Select workspace billing columns via the injected PostgREST client."""
    result = client.table("workspaces").select("id,plan_tier,subscription_status").execute()
    data = getattr(result, "data", result)
    if not isinstance(data, list):
        return []
    loaded: list[WorkspaceEntitlement] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        parsed = parse_workspace_row(row)
        if parsed is not None:
            loaded.append(parsed)
    floors = load_workspace_plan_floors(client)
    if not floors:
        return loaded
    attached: list[WorkspaceEntitlement] = []
    for ws in loaded:
        floor = floors.get(ws.workspace_id)
        if floor is None:
            attached.append(ws)
        else:
            attached.append(ws.model_copy(update={"plan_floor": floor}))
    return attached


def run_overlay_cron(
    *,
    store: JobRunStore,
    workspaces: Sequence[WorkspaceEntitlement],
    run_date: date,
    byok: OverlayByokProbe | None = None,
) -> OverlayCronReport:
    """Dispatch overlay_daily for each non-reserved workspace. Does not invoke the graph."""
    rows: list[OverlayCronRow] = []
    claimed = 0
    skipped = 0
    targets = overlay_cron_targets(workspaces)
    for workspace in targets:
        result: DispatchResult = dispatch_overlay_daily(
            store=store,
            workspace=workspace,
            run_date=run_date,
            byok=byok,
        )
        reason = result.skip_reason.value if result.skip_reason is not None else None
        if result.claimed:
            claimed += 1
        if result.job.status.value == "skipped":
            skipped += 1
        rows.append(
            OverlayCronRow(
                workspace_id=workspace.workspace_id,
                claimed=result.claimed,
                status=result.job.status.value,
                skip_reason=reason,
            )
        )
    return OverlayCronReport(
        run_date=run_date,
        considered=len(workspaces),
        dispatched=len(targets),
        claimed=claimed,
        skipped=skipped,
        rows=tuple(rows),
    )


def _supabase_client_from_env(environ: Mapping[str, str]) -> object:
    """Build a live client. Inline import: ``supabase`` is an optional extra."""
    url = (environ.get("SUPABASE_URL") or environ.get("CORE_SUPABASE_URL") or "").strip()
    key = (
        environ.get("SUPABASE_SERVICE_ROLE_KEY") or environ.get("CORE_SUPABASE_SERVICE_KEY") or ""
    ).strip()
    from supabase import create_client  # deferred — optional extra; tests inject store/client

    return create_client(url, key)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m digiquant.dashboard.overlay")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 2 with OVERLAY_STORE_NOT_CONFIGURED when admin env is empty",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print candidate counts; do not write job_runs",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Dispatch every non-house/system workspace (skipped rows for misses)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run claimed jobs through the one dashboard graph (refuses chain=None)",
    )
    parser.add_argument("--workspace-id", default=None, help="Dispatch a single workspace id")
    parser.add_argument("--run-date", default=None, help="ISO date (default UTC today)")
    return parser.parse_args(argv)


def _load_rows(
    *,
    workspaces: Sequence[WorkspaceEntitlement] | None,
    load_workspaces: Callable[[], Sequence[WorkspaceEntitlement]] | None,
    environ: Mapping[str, str],
    missing: list[str],
) -> list[WorkspaceEntitlement] | str:
    if workspaces is not None:
        return list(workspaces)
    if load_workspaces is not None:
        return list(load_workspaces())
    if missing:
        return format_overlay_store_not_configured(missing)
    return load_overlay_cron_workspaces(_supabase_client_from_env(environ))


def _resolve_store(
    *,
    store: JobRunStore | None,
    build_store: Callable[[], JobRunStore] | None,
    environ: Mapping[str, str],
    missing: list[str],
) -> JobRunStore | str:
    if store is not None:
        return store
    if build_store is not None:
        return build_store()
    if missing:
        return format_overlay_store_not_configured(missing)
    return SupabaseJobRunStore(_supabase_client_from_env(environ))


def _log_dry_run(
    log: Callable[[str], None],
    *,
    loaded: Sequence[WorkspaceEntitlement],
    run_date: date,
    byok_workspace_ids: set[UUID] | None = None,
    persist_enabled: bool = False,
) -> None:
    targets = overlay_cron_targets(loaded)
    entitled = [ws for ws in targets if overlay_billing_entitled(ws)]
    present = byok_workspace_ids or set()
    ready = sum(1 for ws in entitled if ws.workspace_id in present)
    log(
        f"overlay dry-run date={run_date.isoformat()} "
        f"considered={len(loaded)} targets={len(targets)} "
        f"billing_active={len(entitled)} byok_present={ready} "
        f"persist_enabled={int(persist_enabled)}"
    )


def _filter_workspace_id(
    loaded: list[WorkspaceEntitlement],
    workspace_id: str,
) -> list[WorkspaceEntitlement] | str:
    wanted = UUID(workspace_id)
    if wanted in reserved_overlay_workspace_ids():
        return "overlay: workspace is reserved (house/system)"
    selected = [ws for ws in loaded if ws.workspace_id == wanted]
    if not selected:
        return "overlay: workspace not found or reserved"
    return selected


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    workspaces: Sequence[WorkspaceEntitlement] | None = None,
    store: JobRunStore | None = None,
    byok: OverlayByokProbe | None = None,
    load_workspaces: Callable[[], Sequence[WorkspaceEntitlement]] | None = None,
    build_store: Callable[[], JobRunStore] | None = None,
    profile_pins: Mapping[UUID, UUID] | None = None,
    load_profile_pin: Callable[[UUID], UUID | None] | None = None,
    chain_factory: OverlayChainFactory | None = None,
    overlay_runner: OverlayRunner | None = None,
    byok_workspace_ids: set[UUID] | None = None,
    log: Callable[[str], None] = print,
    log_err: Callable[[str], None] | None = None,
) -> int:
    """CLI entry used by ``python -m digiquant.dashboard.overlay``."""
    args = _parse_args(argv)
    err = log_err or (lambda msg: print(msg, file=sys.stderr))
    env = os.environ if environ is None else environ
    missing = missing_overlay_cron_env_names(env)
    if args.check:
        if missing:
            err(format_overlay_store_not_configured(missing))
            return 2
        log("overlay: store env present (names only; dispatch not attempted)")
        return 0
    if not args.dry_run and not args.all and not args.workspace_id:
        err(
            "overlay: pass --dry-run, --workspace-id, or --all "
            "(refusing implicit writes to job_runs)"
        )
        return 2

    loaded = _load_rows(
        workspaces=workspaces,
        load_workspaces=load_workspaces,
        environ=env,
        missing=missing,
    )
    if isinstance(loaded, str):
        err(loaded)
        return 2
    if args.workspace_id:
        loaded = _filter_workspace_id(loaded, args.workspace_id)
        if isinstance(loaded, str):
            err(loaded)
            return 3

    run_date = date.fromisoformat(args.run_date) if args.run_date else datetime.now(tz=UTC).date()
    if args.dry_run:
        present = byok_workspace_ids
        if present is None and workspaces is None and not missing:
            try:
                present = load_active_byok_workspace_ids(_supabase_client_from_env(env))
            except Exception:
                present = set()
        _log_dry_run(
            log,
            loaded=loaded,
            run_date=run_date,
            byok_workspace_ids=present,
            persist_enabled=overlay_persist_enabled(env),
        )
        return 0

    if args.execute and overlay_runner is None and store is None and build_store is None:
        exec_missing = missing_overlay_execute_env_names(env, store_missing=missing)
        if exec_missing:
            err(format_overlay_execute_not_configured(exec_missing))
            return 2

    resolved = _resolve_store(store=store, build_store=build_store, environ=env, missing=missing)
    if isinstance(resolved, str):
        err(resolved)
        return 2
    report = run_overlay_cron(
        store=resolved,
        workspaces=loaded,
        run_date=run_date,
        byok=byok,
    )
    log(
        f"overlay cron date={report.run_date.isoformat()} "
        f"dispatched={report.dispatched} claimed={report.claimed} skipped={report.skipped}"
    )
    if not args.execute:
        return 0
    client = None
    need_client = overlay_runner is None or (profile_pins is None and load_profile_pin is None)
    if need_client and not missing:
        client = _supabase_client_from_env(env)
    return execute_claimed_rows(
        claimed_workspace_ids=tuple(row.workspace_id for row in report.rows if row.claimed),
        store=resolved,
        run_date=run_date,
        profile_pins=profile_pins,
        load_profile_pin=load_profile_pin,
        chain_factory=chain_factory,
        overlay_runner=overlay_runner,
        client=client,
        log_err=err,
    )


__all__ = [
    "OverlayCronReport",
    "OverlayCronRow",
    "format_overlay_store_not_configured",
    "load_active_byok_workspace_ids",
    "load_overlay_cron_workspaces",
    "load_workspace_plan_floors",
    "main",
    "missing_overlay_cron_env_names",
    "overlay_cron_targets",
    "parse_workspace_row",
    "reserved_overlay_workspace_ids",
    "run_overlay_cron",
]
