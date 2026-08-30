"""Kairos broker-mirror sync cron — paper Alpaca only (K4).

Production entry: ``python -m digiquant.olympus.kairos.sync_cron``. House and
system workspaces, live env rows, and inactive connections are never synced.
IBKR paper is listed then held (brokerage session is not opened from cron).
This module does not import Alpaca/IBKR adapters at module level.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from digiquant.brokers.connections import (
    AuthKind,
    Broker,
    ConnectionEnv,
    ConnectionStatus,
)
from digiquant.olympus.tenancy import house_workspace_id, system_workspace_id
from digiquant.vault.envelope import MASTER_KEY_ENV

_FINGERPRINT_SELECT = "id,workspace_id,broker,env,auth_kind,status,fingerprint"
IBKR_HOLD_REASON = "ibkr_requires_brokerage_session"


class SyncTarget(BaseModel):
    """Display-safe connection identity for cron planning (no ciphertext)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    connection_id: UUID
    workspace_id: UUID
    broker: Broker
    env: ConnectionEnv
    auth_kind: AuthKind
    status: ConnectionStatus
    fingerprint: str = Field(pattern=r"^[0-9a-f]{8}$")


class KairosSyncHold(BaseModel):
    """A connection considered then held without adapter construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    connection_id: UUID
    workspace_id: UUID
    reason: str


def reserved_sync_workspace_ids() -> frozenset[UUID]:
    return frozenset({house_workspace_id(), system_workspace_id()})


def parse_connection_row(row: dict[str, object]) -> SyncTarget | None:
    """Build a target from a fingerprint select. Invalid rows skipped."""
    try:
        return SyncTarget(
            connection_id=UUID(str(row["id"])),
            workspace_id=UUID(str(row["workspace_id"])),
            broker=Broker(str(row["broker"])),
            env=ConnectionEnv(str(row["env"])),
            auth_kind=AuthKind(str(row["auth_kind"])),
            status=ConnectionStatus(str(row["status"])),
            fingerprint=str(row["fingerprint"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def kairos_sync_targets(rows: Sequence[SyncTarget]) -> tuple[SyncTarget, ...]:
    """Active paper connections on non-house/system workspaces."""
    reserved = reserved_sync_workspace_ids()
    return tuple(
        row
        for row in rows
        if row.workspace_id not in reserved
        and row.env is ConnectionEnv.PAPER
        and row.status is ConnectionStatus.ACTIVE
    )


def plan_kairos_sync(
    rows: Sequence[SyncTarget],
) -> tuple[tuple[SyncTarget, ...], tuple[KairosSyncHold, ...]]:
    """Split paper-active non-reserved targets into Alpaca runnable vs IBKR held."""
    runnable: list[SyncTarget] = []
    held: list[KairosSyncHold] = []
    for row in kairos_sync_targets(rows):
        if row.broker is Broker.IBKR:
            held.append(
                KairosSyncHold(
                    connection_id=row.connection_id,
                    workspace_id=row.workspace_id,
                    reason=IBKR_HOLD_REASON,
                )
            )
            continue
        runnable.append(row)
    return tuple(runnable), tuple(held)


def missing_kairos_sync_env_names(environ: Mapping[str, str] | None = None) -> list[str]:
    """Store env *names* that are empty. Never returns values."""
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


def missing_kairos_sync_apply_env_names(environ: Mapping[str, str] | None = None) -> list[str]:
    """Store + vault names required to unseal and poll. Never returns values."""
    env = os.environ if environ is None else environ
    missing = missing_kairos_sync_env_names(env)
    if not (env.get(MASTER_KEY_ENV) or "").strip():
        missing.append(MASTER_KEY_ENV)
    return missing


def format_kairos_sync_not_configured(missing: Sequence[str]) -> str:
    return "KAIROS_SYNC_NOT_CONFIGURED: " + ", ".join(missing)


def load_kairos_sync_targets(client: object) -> list[SyncTarget]:
    """Select fingerprint columns only — ciphertext never leaves PostgREST here."""
    result = client.table("broker_connections").select(_FINGERPRINT_SELECT).execute()
    data = getattr(result, "data", result)
    if not isinstance(data, list):
        return []
    loaded: list[SyncTarget] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        parsed = parse_connection_row(row)
        if parsed is not None:
            loaded.append(parsed)
    return loaded


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m digiquant.olympus.kairos.sync_cron")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 2 with KAIROS_SYNC_NOT_CONFIGURED when admin store env is empty",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print candidate counts; do not unseal or poll brokers",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Sync every eligible Alpaca paper connection (IBKR held)",
    )
    parser.add_argument(
        "--connection-id",
        default=None,
        help="Sync a single connection id",
    )
    return parser.parse_args(argv)


def _load_rows(
    *,
    targets: Sequence[SyncTarget] | None,
    load_targets: Callable[[], Sequence[SyncTarget]] | None,
    environ: Mapping[str, str],
    missing: list[str],
) -> list[SyncTarget] | str:
    if targets is not None:
        return list(targets)
    if load_targets is not None:
        return list(load_targets())
    if missing:
        return format_kairos_sync_not_configured(missing)
    return load_kairos_sync_targets(_supabase_client_from_env(environ))


def _supabase_client_from_env(environ: Mapping[str, str]) -> object:
    url = (environ.get("SUPABASE_URL") or environ.get("CORE_SUPABASE_URL") or "").strip()
    key = (
        environ.get("SUPABASE_SERVICE_ROLE_KEY") or environ.get("CORE_SUPABASE_SERVICE_KEY") or ""
    ).strip()
    from supabase import create_client  # deferred — optional extra; tests inject targets

    return create_client(url, key)


def _filter_connection_id(
    loaded: list[SyncTarget],
    connection_id: str,
) -> list[SyncTarget] | str:
    try:
        wanted = UUID(connection_id)
    except ValueError:
        return "kairos sync: connection not found"
    selected = [row for row in loaded if row.connection_id == wanted]
    if not selected:
        return "kairos sync: connection not found"
    row = selected[0]
    if row.workspace_id in reserved_sync_workspace_ids():
        return "kairos sync: connection workspace is reserved (house/system)"
    if row.env is ConnectionEnv.LIVE:
        return "kairos sync: live env is not authorized"
    return selected


def _log_dry_run(
    log: Callable[[str], None],
    *,
    loaded: Sequence[SyncTarget],
) -> None:
    runnable, held = plan_kairos_sync(loaded)
    log(
        f"kairos sync dry-run considered={len(loaded)} "
        f"targets={len(kairos_sync_targets(loaded))} "
        f"runnable={len(runnable)} ibkr_held={len(held)}"
    )


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    targets: Sequence[SyncTarget] | None = None,
    load_targets: Callable[[], Sequence[SyncTarget]] | None = None,
    sync_batch: Callable[[Sequence[SyncTarget]], int] | None = None,
    log: Callable[[str], None] = print,
    log_err: Callable[[str], None] | None = None,
) -> int:
    """CLI entry used by ``python -m digiquant.olympus.kairos.sync_cron``."""
    args = _parse_args(argv)
    err = log_err or (lambda msg: print(msg, file=sys.stderr))
    env = os.environ if environ is None else environ
    missing_store = missing_kairos_sync_env_names(env)
    if args.check:
        if missing_store:
            err(format_kairos_sync_not_configured(missing_store))
            return 2
        log("kairos sync: store env present (names only; poll not attempted)")
        return 0
    if not args.dry_run and not args.all and not args.connection_id:
        err(
            "kairos sync: pass --dry-run, --connection-id, or --all "
            "(refusing implicit broker polls)"
        )
        return 2

    loaded = _load_rows(
        targets=targets,
        load_targets=load_targets,
        environ=env,
        missing=missing_store,
    )
    if isinstance(loaded, str):
        err(loaded)
        return 2
    if args.connection_id:
        loaded = _filter_connection_id(loaded, args.connection_id)
        if isinstance(loaded, str):
            err(loaded)
            return 3

    if args.dry_run:
        _log_dry_run(log, loaded=loaded)
        return 0

    runnable, held = plan_kairos_sync(loaded)
    if sync_batch is not None:
        synced = sync_batch(runnable)
        log(f"kairos sync runnable={len(runnable)} synced={synced} ibkr_held={len(held)}")
        return 0
    apply_missing = missing_kairos_sync_apply_env_names(env)
    if apply_missing:
        err(format_kairos_sync_not_configured(apply_missing))
        return 2
    synced = _production_sync_batch(runnable, environ=env)
    log(f"kairos sync runnable={len(runnable)} synced={synced} ibkr_held={len(held)}")
    return 0


def _production_sync_batch(
    runnable: Sequence[SyncTarget],
    *,
    environ: Mapping[str, str],
) -> int:
    """Unseal Alpaca paper connections and poll fills. Lazy adapter import."""
    alpaca_paper = [
        target
        for target in runnable
        if target.broker is Broker.ALPACA
        and target.env is ConnectionEnv.PAPER
        and target.status is ConnectionStatus.ACTIVE
        and target.workspace_id not in reserved_sync_workspace_ids()
    ]
    if not alpaca_paper:
        return 0
    from digiquant.brokers.alpaca import AlpacaAdapter, ApiKeyAuth, OAuthAuth
    from digiquant.brokers.base import BrokerAdapter
    from digiquant.brokers.connections import BrokerConnection, get_connection, open_credential
    from digiquant.olympus.kairos.sync import SyncCursor, run_sync_batch
    from digiquant.vault.envelope import ApiKeyCredential, OAuthCredential

    client = _supabase_client_from_env(environ)
    cursor = SyncCursor(fills_since=datetime.now(tz=UTC) - timedelta(days=7))
    cycles: list[tuple[BrokerAdapter, BrokerConnection, SyncCursor]] = []
    reserved = reserved_sync_workspace_ids()
    for target in alpaca_paper:
        connection = get_connection(
            client=client,
            workspace_id=target.workspace_id,
            broker=target.broker,
            env=target.env,
        )
        if (
            connection.id != target.connection_id
            or connection.workspace_id in reserved
            or connection.broker is not Broker.ALPACA
            or connection.env is not ConnectionEnv.PAPER
            or connection.status is not ConnectionStatus.ACTIVE
        ):
            continue
        with open_credential(client=client, connection=connection) as lease:
            cred = lease.credential
            if isinstance(cred, OAuthCredential):
                auth: ApiKeyAuth | OAuthAuth = OAuthAuth(access_token=cred.access_token)
            elif isinstance(cred, ApiKeyCredential):
                auth = ApiKeyAuth(key_id=cred.key_id, secret=cred.secret)
            else:
                continue
            adapter = AlpacaAdapter(auth, env="paper")
        cycles.append((adapter, connection, cursor))
    if not cycles:
        return 0
    results = run_sync_batch(client=client, cycles=cycles)
    return sum(item.fills_appended for item in results)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "IBKR_HOLD_REASON",
    "KairosSyncHold",
    "SyncTarget",
    "format_kairos_sync_not_configured",
    "kairos_sync_targets",
    "load_kairos_sync_targets",
    "main",
    "missing_kairos_sync_apply_env_names",
    "missing_kairos_sync_env_names",
    "parse_connection_row",
    "plan_kairos_sync",
    "reserved_sync_workspace_ids",
]
