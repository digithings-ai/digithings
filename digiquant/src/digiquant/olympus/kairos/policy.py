"""Venue resolution policy for Kairos order routing (K4).

``resolve_venue`` is the single gate between an approved ``OrderIntent`` and a
concrete :class:`~digiquant.brokers.contracts.ExecutionVenue`. v1 deliberately
does **not** store an execution-policy column on ``workspaces`` (T0's table is
untouched by this work package; a richer stored policy lands with T4). Instead
venue is resolved from:

1. **House / system** — ``workspace_id is None`` **or** the well-known
   ``house_workspace_id()`` / ``system_workspace_id()`` UUIDs → always
   :attr:`~digiquant.brokers.contracts.ExecutionVenue.PAPER_INTERNAL`,
   hard-coded, not configurable. Those identities can never route externally.
2. **Kill switch** ``OLYMPUS_KAIROS_ROUTING`` (default **off** / absent) → only
   ``PAPER_INTERNAL`` is reachable regardless of connections. Polarity is the
   inverse of ``OLYMPUS_PORTFOLIO_LEDGER`` (ledger defaults on; routing defaults
   off) because external submit is a human-gated surface.
3. **Active paper connection** (kill switch on) → the matching paper venue
   (``alpaca`` → ``ALPACA_PAPER``, ``ibkr`` → ``IBKR_PAPER``). Exactly one active
   paper broker is required; zero → ``PAPER_INTERNAL``; two or more →
   :class:`AmbiguousVenueError`. Live broker / venue names in
   ``active_paper_brokers`` raise
   :class:`~digiquant.brokers.contracts.LiveVenueNotAuthorizedError` on the
   public API (not a bare ``ValueError``).
4. **Any ``*_LIVE`` value** attempting to leave this function →
   :class:`~digiquant.brokers.contracts.LiveVenueNotAuthorizedError`
   (test-pinned invariant on the public path). Live is enumerated on
   ``ExecutionVenue`` for vocabulary completeness only; nothing here ever
   returns one.

Callers that need to look up connections do so themselves (via
:mod:`digiquant.brokers.connections`) and pass the resulting broker names into
``active_paper_brokers`` — this module performs **no I/O**, so policy unit tests
stay free of a fake Supabase client.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from uuid import UUID

from digiquant.brokers.connections import Broker
from digiquant.brokers.contracts import ExecutionVenue, LiveVenueNotAuthorizedError
from digiquant.olympus.tenancy import house_workspace_id, system_workspace_id

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
_LIVE_VENUE_VALUES = frozenset(v.value for v in _LIVE_VENUES)


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


class ForeignWorkspaceIntentError(ValueError):
    """A ledger row the router would consume does not match the connection workspace.

    The router is an authority boundary: it may only act on
    ``connection.workspace_id``'s intents. A missing or mismatched
    ``workspace_id`` on a consumed row is refused loudly — never skipped as a
    quiet no-op that could hide a tenancy bug.
    """


def routing_enabled_in(environ: Mapping[str, str]) -> bool:
    """Whether ``OLYMPUS_KAIROS_ROUTING`` is on in ``environ``. Defaults off."""
    return environ.get(_ROUTING_ENV, "").strip().lower() in _ON_VALUES


def routing_enabled() -> bool:
    """Whether external venue routing is reachable. Defaults to **off**.

    Unset / empty / any value outside :data:`_ON_VALUES` means off. With the
    switch off, :func:`resolve_venue` returns only ``PAPER_INTERNAL`` — the
    internal paper path is unchanged and house regression stays byte-identical.
    """
    return routing_enabled_in(os.environ)


def is_house_or_system_workspace(workspace_id: UUID | None) -> bool:
    """True for ``None`` and the well-known house / system workspace UUIDs."""
    if workspace_id is None:
        return True
    return workspace_id in {house_workspace_id(), system_workspace_id()}


def _reject_live_token(raw: str) -> None:
    """Raise :class:`LiveVenueNotAuthorizedError` for live venue / broker tokens."""
    text = raw.strip().lower()
    if text in _LIVE_VENUE_VALUES or text.endswith("_live") or text == "live":
        raise LiveVenueNotAuthorizedError(
            f"resolve_venue refused live token {raw!r}; "
            "live routing is not authorized in this program"
        )


def _coerce_broker(raw: Broker | str | ExecutionVenue) -> Broker:
    """Coerce a paper broker token; live tokens raise on the public API."""
    if isinstance(raw, Broker):
        return raw
    if isinstance(raw, ExecutionVenue):
        _assert_not_live(raw)
        # Map paper venues back to brokers; PAPER_INTERNAL is not a broker.
        for broker, venue in _BROKER_TO_PAPER_VENUE.items():
            if raw is venue:
                return broker
        raise LiveVenueNotAuthorizedError(
            f"resolve_venue refused venue {raw.value!r}; "
            "only paper broker venues may appear in active_paper_brokers"
        )
    text = str(raw).strip().lower()
    _reject_live_token(text)
    try:
        return Broker(text)
    except ValueError as exc:
        if "live" in text:
            raise LiveVenueNotAuthorizedError(
                f"resolve_venue refused live token {raw!r}; "
                "live routing is not authorized in this program"
            ) from exc
        raise


def resolve_venue(
    workspace_id: UUID | None,
    *,
    active_paper_brokers: Sequence[Broker | str | ExecutionVenue] = (),
) -> ExecutionVenue:
    """Resolve the execution venue for a workspace (or the house book).

    Parameters
    ----------
    workspace_id:
        ``None``, ``house_workspace_id()``, or ``system_workspace_id()`` → always
        ``PAPER_INTERNAL`` (hard-coded). Caller must pass the identity through
        unchanged — do not substitute a connection's workspace for ``None``.
    active_paper_brokers:
        Brokers with an **active** ``broker_connections`` row in the ``paper``
        env for this workspace. Ignored when the kill switch is off or when the
        workspace is house/system. Live venue / broker tokens raise
        :class:`LiveVenueNotAuthorizedError` (public-API contract).

    Returns
    -------
    ExecutionVenue
        Never a ``*_LIVE`` member.

    Raises
    ------
    AmbiguousVenueError
        Kill switch on, tenant workspace, and two or more distinct paper brokers
        are active.
    LiveVenueNotAuthorizedError
        Any live venue / broker token in ``active_paper_brokers``, or any path
        that would produce a ``*_LIVE`` venue.
    """
    if is_house_or_system_workspace(workspace_id):
        # Still reject live tokens so the public API never silently accepts them
        # even when the workspace hard-codes PAPER_INTERNAL.
        if active_paper_brokers:
            tuple(_coerce_broker(b) for b in active_paper_brokers)
        return ExecutionVenue.PAPER_INTERNAL

    # Validate live tokens before the kill-switch early return so
    # ``resolve_venue(..., active_paper_brokers=["alpaca_live"])`` raises
    # ``LiveVenueNotAuthorizedError`` on the public API regardless of env.
    brokers = tuple(dict.fromkeys(_coerce_broker(b) for b in active_paper_brokers))

    if not routing_enabled():
        return ExecutionVenue.PAPER_INTERNAL

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
    """Raise if ``venue`` is any ``*_LIVE`` member — defense-in-depth."""
    if venue in _LIVE_VENUES or venue.value.endswith("_live"):
        raise LiveVenueNotAuthorizedError(
            f"resolve_venue refused live venue {venue.value!r}; "
            "live routing is not authorized in this program"
        )


__all__ = [
    "AmbiguousVenueError",
    "ForeignWorkspaceIntentError",
    "InconsistentOrderChainError",
    "is_house_or_system_workspace",
    "routing_enabled",
    "routing_enabled_in",
    "resolve_venue",
]
