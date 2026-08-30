"""Venue resolution policy for Kairos order routing (K4).

``resolve_venue`` is the single gate between an approved ``OrderIntent`` and a
concrete :class:`~digiquant.brokers.contracts.ExecutionVenue`. v1 deliberately
does **not** store an execution-policy column on ``workspaces`` (T0's table is
untouched by this work package; a richer stored policy lands with T4). Instead
venue is resolved from:

1. **House / system** (``workspace_id is None``) → always
   :attr:`~digiquant.brokers.contracts.ExecutionVenue.PAPER_INTERNAL`,
   hard-coded, not configurable.
2. **Kill switch** ``OLYMPUS_KAIROS_ROUTING`` (default **off** / absent) → only
   ``PAPER_INTERNAL`` is reachable regardless of connections. Polarity is the
   inverse of ``OLYMPUS_PORTFOLIO_LEDGER`` (ledger defaults on; routing defaults
   off) because external submit is a human-gated surface.
3. **Active paper connection** (kill switch on) → the matching paper venue
   (``alpaca`` → ``ALPACA_PAPER``, ``ibkr`` → ``IBKR_PAPER``). Exactly one active
   paper broker is required; zero → ``PAPER_INTERNAL``; two or more →
   :class:`AmbiguousVenueError`.
4. **Any ``*_LIVE`` value** attempting to leave this function →
   :class:`~digiquant.brokers.contracts.LiveVenueNotAuthorizedError`
   (test-pinned invariant). Live is enumerated on ``ExecutionVenue`` for
   vocabulary completeness only; nothing here ever returns one.

Callers that need to look up connections do so themselves (via
:mod:`digiquant.brokers.connections`) and pass the resulting broker names into
``active_paper_brokers`` — this module performs **no I/O**, so policy unit tests
stay free of a fake Supabase client.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from uuid import UUID

from digiquant.brokers.connections import Broker
from digiquant.brokers.contracts import ExecutionVenue, LiveVenueNotAuthorizedError

_ROUTING_ENV = "OLYMPUS_KAIROS_ROUTING"
# Opt-in (default off). Mirror the *shape* of ledger_io's env parse, not its polarity.
_ON_VALUES = frozenset({"1", "on", "true", "yes", "enabled"})

_BROKER_TO_PAPER_VENUE: dict[Broker, ExecutionVenue] = {
    Broker.ALPACA: ExecutionVenue.ALPACA_PAPER,
    Broker.IBKR: ExecutionVenue.IBKR_PAPER,
}

_LIVE_VENUES = frozenset(
    {
        ExecutionVenue.ALPACA_LIVE,
        ExecutionVenue.IBKR_LIVE,
    }
)


class AmbiguousVenueError(ValueError):
    """More than one active paper broker connection is present for a workspace.

    v1 has no stored preference ordering on ``workspaces``. Refusing to guess is
    the honest behaviour until T4 ships a real execution-policy column.
    """


class InconsistentOrderChainError(ValueError):
    """A pending ``OrderIntent`` is chained to a ``NO_OP`` / ``REJECT`` decision.

    Direction lives on ``DecisionIntent.action`` three hops up the ledger chain
    (:func:`digiquant.olympus.hermes.writers.execution_io._directions_by_order`).
    ``NO_OP`` / ``REJECT`` imply no order at all — a pending intent under either
    is a broken chain, and the router refuses to invent a side.
    """


def routing_enabled() -> bool:
    """Whether external venue routing is reachable. Defaults to **off**.

    Unset / empty / any value outside :data:`_ON_VALUES` means off. With the
    switch off, :func:`resolve_venue` returns only ``PAPER_INTERNAL`` — the
    internal paper path is unchanged and house regression stays byte-identical.
    """
    return os.environ.get(_ROUTING_ENV, "").strip().lower() in _ON_VALUES


def _coerce_broker(raw: Broker | str) -> Broker:
    return raw if isinstance(raw, Broker) else Broker(str(raw).strip().lower())


def resolve_venue(
    workspace_id: UUID | None,
    *,
    active_paper_brokers: Sequence[Broker | str] = (),
) -> ExecutionVenue:
    """Resolve the execution venue for a workspace (or the house book).

    Parameters
    ----------
    workspace_id:
        ``None`` for the house / system cron path — always ``PAPER_INTERNAL``.
    active_paper_brokers:
        Brokers with an **active** ``broker_connections`` row in the ``paper``
        env for this workspace. Ignored when the kill switch is off or when
        ``workspace_id is None``. Pass the result of listing connections; do
        not pass live-env brokers (they are ignored here and live venues can
        never be returned).

    Returns
    -------
    ExecutionVenue
        Never a ``*_LIVE`` member. Raising on live is the test-pinned invariant
        that keeps this function honest if a future caller tries to force one
        through ``active_paper_brokers`` via an unexpected mapping.

    Raises
    ------
    AmbiguousVenueError
        Kill switch on, workspace set, and two or more distinct paper brokers
        are active.
    LiveVenueNotAuthorizedError
        Internal invariant: any path that would produce a ``*_LIVE`` venue.
    """
    if workspace_id is None:
        return ExecutionVenue.PAPER_INTERNAL

    if not routing_enabled():
        return ExecutionVenue.PAPER_INTERNAL

    brokers = tuple(dict.fromkeys(_coerce_broker(b) for b in active_paper_brokers))
    if not brokers:
        return ExecutionVenue.PAPER_INTERNAL
    if len(brokers) > 1:
        names = ", ".join(b.value for b in brokers)
        raise AmbiguousVenueError(
            f"workspace {workspace_id} has multiple active paper brokers ({names}); "
            "v1 refuses to pick — set a single active connection or wait for T4 "
            "execution policy"
        )

    venue = _BROKER_TO_PAPER_VENUE[brokers[0]]
    _assert_not_live(venue)
    return venue


def _assert_not_live(venue: ExecutionVenue) -> None:
    """Raise if ``venue`` is any ``*_LIVE`` member — test-pinned invariant."""
    if venue in _LIVE_VENUES or venue.value.endswith("_live"):
        raise LiveVenueNotAuthorizedError(
            f"resolve_venue refused live venue {venue.value!r}; "
            "live routing is not authorized in this program"
        )


__all__ = [
    "AmbiguousVenueError",
    "InconsistentOrderChainError",
    "routing_enabled",
    "resolve_venue",
]
