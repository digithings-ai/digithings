"""Kairos order-intent route cron — Alpaca paper OAuth only (K4).

Production entry: ``python -m digiquant.olympus.kairos.route_cron``. Overlay
books persist order intents; this CLI is the missing submit seam. House and
system workspaces, live env rows, IBKR paper, and Alpaca ``api_key`` rows are
never submitted. ``OLYMPUS_KAIROS_ROUTING`` defaults **off** — ``--all`` then
exits 3 without calling ``submit_order``. This module does not import Alpaca
adapters at module level.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from digiquant.brokers.connections import AuthKind, Broker, ConnectionEnv, ConnectionStatus
from digiquant.olympus.kairos.policy import routing_enabled_in
from digiquant.olympus.kairos.sync_cron import (
    ALPACA_API_KEY_HOLD_REASON,
    IBKR_HOLD_REASON,
    SyncTarget,
    _filter_connection_id,
    _hold_count,
    _load_rows,
    _supabase_client_from_env,
    format_kairos_sync_not_configured,
    kairos_sync_targets,
    missing_kairos_sync_apply_env_names,
    missing_kairos_sync_env_names,
    plan_kairos_sync,
    reserved_sync_workspace_ids,
)

EXIT_NOT_CONFIGURED: int = 2
EXIT_ROUTING_DISABLED: int = 3
EXIT_REFUSED: int = 4
KAIROS_ROUTING_DISABLED: str = "KAIROS_ROUTING_DISABLED"

RouteBatchFn = Callable[[Sequence[SyncTarget]], int]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m digiquant.olympus.kairos.route_cron")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 2 when admin store env is empty; log routing kill-switch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print candidate counts; do not unseal or submit orders",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Route every eligible Alpaca paper OAuth connection (IBKR held)",
    )
    parser.add_argument(
        "--connection-id",
        default=None,
        help="Route a single connection id",
    )
    return parser.parse_args(argv)


def _filter_route_connection_id(
    loaded: list[SyncTarget],
    connection_id: str,
) -> list[SyncTarget] | str:
    """Same eligibility as sync; operator errors say ``kairos route``."""
    selected = _filter_connection_id(loaded, connection_id)
    if isinstance(selected, str):
        return selected.replace("kairos sync:", "kairos route:", 1)
    return selected


def _log_dry_run(
    log: Callable[[str], None],
    *,
    loaded: Sequence[SyncTarget],
    routing_on: bool,
) -> None:
    runnable, held = plan_kairos_sync(loaded)
    flag = "true" if routing_on else "false"
    log(
        f"kairos route dry-run routing_enabled={flag} considered={len(loaded)} "
        f"targets={len(kairos_sync_targets(loaded))} "
        f"runnable={len(runnable)} "
        f"ibkr_held={_hold_count(held, IBKR_HOLD_REASON)} "
        f"alpaca_api_key_held={_hold_count(held, ALPACA_API_KEY_HOLD_REASON)}"
    )


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    targets: Sequence[SyncTarget] | None = None,
    load_targets: Callable[[], Sequence[SyncTarget]] | None = None,
    route_batch: RouteBatchFn | None = None,
    log: Callable[[str], None] = print,
    log_err: Callable[[str], None] | None = None,
) -> int:
    """CLI entry used by ``python -m digiquant.olympus.kairos.route_cron``."""
    err = log_err or (lambda msg: print(msg, file=sys.stderr))
    if argv is None:
        args_list = sys.argv[1:]
    else:
        args_list = list(argv)
    joined = " ".join(args_list).lower()
    if "dispatch" in joined or "--apply" in joined:
        err("kairos route: refuses workflow_dispatch / --apply")
        return EXIT_REFUSED
    args = _parse_args(args_list)
    env = os.environ if environ is None else environ
    routing_on = routing_enabled_in(env)
    missing_store = missing_kairos_sync_env_names(env)
    if args.check:
        if missing_store:
            err(format_kairos_sync_not_configured(missing_store))
            return EXIT_NOT_CONFIGURED
        flag = "true" if routing_on else "false"
        log(f"kairos route: store env present routing_enabled={flag}")
        return 0
    if not args.dry_run and not args.all and not args.connection_id:
        err(
            "kairos route: pass --dry-run, --connection-id, or --all "
            "(refusing implicit order submits)"
        )
        return EXIT_NOT_CONFIGURED

    if args.dry_run:
        loaded = _load_rows(
            targets=targets,
            load_targets=load_targets,
            environ=env,
            missing=missing_store,
        )
        if isinstance(loaded, str):
            err(loaded)
            return EXIT_NOT_CONFIGURED
        _log_dry_run(log, loaded=loaded, routing_on=routing_on)
        return 0

    if not routing_on:
        err(f"{KAIROS_ROUTING_DISABLED}: OLYMPUS_KAIROS_ROUTING is off (no submit_order)")
        return EXIT_ROUTING_DISABLED

    loaded = _load_rows(
        targets=targets,
        load_targets=load_targets,
        environ=env,
        missing=missing_store,
    )
    if isinstance(loaded, str):
        err(loaded)
        return EXIT_NOT_CONFIGURED
    if args.connection_id:
        loaded = _filter_route_connection_id(loaded, args.connection_id)
        if isinstance(loaded, str):
            err(loaded)
            return EXIT_ROUTING_DISABLED

    runnable, held = plan_kairos_sync(loaded)
    if route_batch is not None:
        routed = route_batch(runnable)
        log(
            f"kairos route routing_enabled=true runnable={len(runnable)} routed={routed} "
            f"ibkr_held={_hold_count(held, IBKR_HOLD_REASON)} "
            f"alpaca_api_key_held={_hold_count(held, ALPACA_API_KEY_HOLD_REASON)}"
        )
        return 0
    apply_missing = missing_kairos_sync_apply_env_names(env)
    if apply_missing:
        err(format_kairos_sync_not_configured(apply_missing))
        return EXIT_NOT_CONFIGURED
    routed = _production_route_batch(runnable, environ=env)
    log(
        f"kairos route routing_enabled=true runnable={len(runnable)} routed={routed} "
        f"ibkr_held={_hold_count(held, IBKR_HOLD_REASON)} "
        f"alpaca_api_key_held={_hold_count(held, ALPACA_API_KEY_HOLD_REASON)}"
    )
    return 0


def _production_route_batch(
    runnable: Sequence[SyncTarget],
    *,
    environ: Mapping[str, str],
) -> int:
    """Unseal Alpaca paper OAuth connections and submit pending overlay intents.

    Adapter import is deferred so unit tests never construct brokers.
    """
    alpaca_paper = [
        target
        for target in runnable
        if target.broker is Broker.ALPACA
        and target.env is ConnectionEnv.PAPER
        and target.status is ConnectionStatus.ACTIVE
        and target.auth_kind is AuthKind.OAUTH
        and target.workspace_id not in reserved_sync_workspace_ids()
    ]
    if not alpaca_paper:
        return 0
    # Deferred: unit tests inject route_batch and must not construct adapters.
    from digiquant.brokers.alpaca import AlpacaAdapter, OAuthAuth
    from digiquant.brokers.connections import get_connection, open_credential
    from digiquant.olympus.kairos.router import route_pending_orders
    from digiquant.vault.envelope import OAuthCredential

    client = _supabase_client_from_env(environ)
    now = datetime.now(tz=UTC)
    today = now.date()
    reserved = reserved_sync_workspace_ids()
    routed = 0
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
            or connection.auth_kind is not AuthKind.OAUTH
        ):
            continue
        with open_credential(client=client, connection=connection) as lease:
            cred = lease.credential
            if not isinstance(cred, OAuthCredential):
                continue
            adapter = AlpacaAdapter(OAuthAuth(access_token=cred.access_token), env="paper")
        result = route_pending_orders(
            client=client,
            adapter=adapter,
            connection=connection,
            run_date=today,
            submitted_date=today,
            now=now,
            workspace_id=connection.workspace_id,
        )
        routed += len(result.routed)
    return routed


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EXIT_NOT_CONFIGURED",
    "EXIT_REFUSED",
    "EXIT_ROUTING_DISABLED",
    "KAIROS_ROUTING_DISABLED",
    "RouteBatchFn",
    "main",
]
