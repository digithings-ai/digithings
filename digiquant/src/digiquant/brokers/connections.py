"""Broker connection store: sealed credentials in `broker_connections` (K3).

At most one *active* row per ``(workspace_id, broker, env)`` holding a credential sealed by
:mod:`digiquant.vault.envelope`. This module owns the four operations the rest of the
program needs — create/seal, get, open (unseal) for the duration of one broker call,
revoke — plus the display-safe listing that is the *only* thing an API or UI may show.

Boundary rules this module enforces
-----------------------------------
1. **Plaintext never lands in a row and never leaves an opened lease.** ``create_*`` takes
   a credential, seals it, and returns a record whose ``repr`` is fingerprint-only;
   :func:`open_credential` hands back a :class:`~digiquant.vault.envelope.CredentialLease`
   that dies with its ``with`` block.
2. **A non-active row fails closed.** Opening a ``revoked``/``expired`` connection raises
   :class:`ConnectionRevokedError` before any decryption is attempted, so revocation is
   effective the moment the row's status changes — it does not depend on the ciphertext
   becoming unreadable.
3. **The AAD is derived from the row, never passed in.** :attr:`BrokerConnection.aad` is
   ``f"{workspace_id}:{broker}:{env}"`` built from the record's own validated fields, so a
   caller cannot accidentally (or deliberately) open row A's ciphertext under row B's
   binding — the whole point of the AAD in the first place.
4. **Listings never fetch the ciphertext.** :func:`list_connection_fingerprints` selects an
   explicit column list that omits ``ciphertext``/``nonce``, so sealed bytes are not even
   put on the wire for a screen that only needs a fingerprint.

Client seam
-----------
:class:`SupabaseClient` is a minimal ``table()`` Protocol, mirroring the pattern in
`dashboard/research/supabase_io.py` rather than importing it: `digiquant.brokers` is the
low-level venue layer and must not depend on the research sub-package (which pulls
the research extra's runtime and, transitively, digigraph). Tests inject a fake — there is no
live database in this suite.

``bytea`` over PostgREST is a text round-trip: Postgres' default ``bytea_output = hex``
means a selected ``bytea`` arrives as the string ``"\\x<hex>"``, and the same form is
accepted on insert. :func:`_encode_bytea` / :func:`_decode_bytea` are that conversion, and
they fail closed on anything that is not exactly that shape rather than guessing — a
mis-parsed nonce or ciphertext would otherwise surface as an opaque authentication failure
much later.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Final, Protocol, TypeAlias
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from digiquant.brokers.contracts import BrokerError
from digiquant.vault.envelope import (
    ApiKeyCredential,
    CredentialLease,
    MasterKey,
    OAuthCredential,
    SealedEnvelope,
    build_aad,
    fingerprint,
    seal_credential,
    unseal_credential,
)

logger = logging.getLogger(__name__)

TABLE_NAME: Final = "broker_connections"

# Explicit column list for display-safe reads: ciphertext and nonce are deliberately
# absent, so a listing cannot leak sealed bytes even if a caller logs the whole row.
_FINGERPRINT_COLUMNS: Final = (
    "id, workspace_id, broker, env, auth_kind, fingerprint, scopes, status, "
    "created_at, revoked_at, last_used_at"
)
_FULL_COLUMNS: Final = (
    "id, workspace_id, broker, env, auth_kind, ciphertext, nonce, key_id, fingerprint, "
    "scopes, status, created_at, revoked_at, last_used_at"
)

_BYTEA_HEX_PREFIX: Final = "\\x"


class Broker(StrEnum):
    """Closed vocabulary of brokers, matching ``broker_connections.broker``'s CHECK."""

    ALPACA = "alpaca"
    IBKR = "ibkr"


class ConnectionEnv(StrEnum):
    """Closed vocabulary of broker environments, matching the ``env`` CHECK.

    ``LIVE`` exists because the column admits it, not because anything in this program
    reaches it: K1/K2 adapters refuse a non-paper env, and routing to a live venue is a
    test-pinned refusal in `contracts.ExecutionVenue`'s consumers.
    """

    PAPER = "paper"
    LIVE = "live"


class AuthKind(StrEnum):
    """Closed vocabulary of sealed payload kinds, matching the ``auth_kind`` CHECK.

    Always derived from the sealed credential's own ``kind`` (see
    :func:`create_connection`) — never accepted as a separate argument, so the column can
    never disagree with the payload it describes.
    """

    OAUTH = "oauth"
    API_KEY = "api_key"


class ConnectionStatus(StrEnum):
    """Closed vocabulary of connection lifecycle states, matching the ``status`` CHECK."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ConnectionStoreError(BrokerError):
    """The `broker_connections` store returned something unusable."""


class ConnectionNotFoundError(ConnectionStoreError):
    """No `broker_connections` row matched the requested identity."""


class ConnectionRevokedError(BrokerError):
    """A connection was opened while not ``active`` — fail closed, never decrypt.

    Raised for ``revoked`` and ``expired`` alike: both mean "this credential is not
    authorized for use right now", and the message names which one it was.
    """


class _ConnectionModel(BaseModel):
    """Strict, immutable base for the records in this module."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("created_at", "revoked_at", "last_used_at", mode="after", check_fields=False)
    @classmethod
    def _normalize_to_utc(cls, value: datetime | None) -> datetime | None:
        """Normalize an aware timestamp to UTC.

        Deliberately different from `contracts.py`'s ``_reject_non_utc``: those fields are
        producer-supplied event times where a non-UTC offset signals a caller bug, while
        these come back from a Postgres ``timestamptz`` — an instant, whose offset is a
        rendering detail. Naive values are still rejected, by the ``AwareDatetime`` type.
        """
        return None if value is None else value.astimezone(UTC)


class BrokerConnection(_ConnectionModel):
    """One `broker_connections` row: a sealed credential plus its lifecycle metadata.

    ``ciphertext``/``nonce`` are ``repr=False`` — sealed bytes are not secret in the way
    plaintext is, but keeping every ``repr`` in the K3 surface fingerprint-only means no
    log line can ever be one refactor away from carrying credential material.

    ``key_id`` names the *master-key version* that sealed this row, not any broker-side
    key identifier; an API key's own ``key_id`` lives sealed inside ``ciphertext``.
    """

    id: UUID
    # No FK: the `workspaces` table does not exist yet (T0 lands it and will constrain
    # this column). Matches the spec §3 sketch's own `-- FK once T0 lands` note.
    workspace_id: UUID
    broker: Broker
    env: ConnectionEnv
    auth_kind: AuthKind
    ciphertext: Annotated[bytes, Field(strict=True, repr=False)]
    nonce: Annotated[bytes, Field(strict=True, repr=False)]
    key_id: Annotated[str, Field(min_length=1, max_length=32)]
    fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{8}$")]
    scopes: tuple[str, ...] = ()
    status: ConnectionStatus
    created_at: AwareDatetime
    revoked_at: AwareDatetime | None = None
    last_used_at: AwareDatetime | None = None

    @property
    def sealed_envelope(self) -> SealedEnvelope:
        """The row's sealed payload, re-validated (nonce/tag lengths) on the way out."""
        return SealedEnvelope(
            ciphertext=self.ciphertext,
            nonce=self.nonce,
            key_id=self.key_id,
        )

    @property
    def aad(self) -> bytes:
        """This row's associated data: ``f"{workspace_id}:{broker}:{env}"``.

        Built from the record's validated fields, so the value is canonical regardless of
        how the caller originally spelled the workspace id (``UUID`` renders lowercase and
        hyphenated) and cannot be substituted with another row's binding.
        """
        return build_aad(str(self.workspace_id), self.broker.value, self.env.value)


class ConnectionFingerprint(_ConnectionModel):
    """Display-safe projection of a connection — the shape an API or UI may return.

    Carries no ciphertext, no nonce, and no key_id: a fingerprint, the lifecycle state,
    and the identity of the connection. There is deliberately no way to widen this into
    the sealed columns; a caller that needs those calls :func:`get_connection`.
    """

    id: UUID
    workspace_id: UUID
    broker: Broker
    env: ConnectionEnv
    auth_kind: AuthKind
    fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{8}$")]
    scopes: tuple[str, ...] = ()
    status: ConnectionStatus
    created_at: AwareDatetime
    revoked_at: AwareDatetime | None = None
    last_used_at: AwareDatetime | None = None


BrokerCredentialPayload: TypeAlias = OAuthCredential | ApiKeyCredential


class PostgrestResponse(Protocol):
    """The one attribute this module reads off a PostgREST response."""

    data: object


class PostgrestQuery(Protocol):
    """The exact subset of the PostgREST fluent chain this module uses.

    Spelling the chain out instead of typing it ``Any`` is what makes the store's request
    shape reviewable: widening a ``select`` or dropping the ``neq`` guard that keeps a
    revoke from moving ``revoked_at`` has to pass through a named surface. ``supabase``
    publishes no types for the builder, so this is a structural description of the calls
    made below — deliberately not the whole builder, which is why it is private-by-intent
    and named for the chain rather than the vendor class.
    """

    def select(self, columns: str) -> PostgrestQuery: ...
    def insert(self, row: Mapping[str, object]) -> PostgrestQuery: ...
    def update(self, values: Mapping[str, object]) -> PostgrestQuery: ...
    def eq(self, column: str, value: object) -> PostgrestQuery: ...
    def neq(self, column: str, value: object) -> PostgrestQuery: ...
    def order(self, column: str, *, desc: bool = False) -> PostgrestQuery: ...
    def limit(self, count: int) -> PostgrestQuery: ...
    def execute(self) -> PostgrestResponse: ...


class SupabaseClient(Protocol):
    """The one method this module uses from the ``supabase`` client.

    A Protocol so tests inject a fake without the ``supabase`` dependency, mirroring
    `dashboard/research/supabase_io.py`.
    """

    def table(self, name: str) -> PostgrestQuery: ...


def _encode_bytea(raw: bytes) -> str:
    """Render bytes as Postgres' hex ``bytea`` literal for a JSON request body."""
    return f"{_BYTEA_HEX_PREFIX}{raw.hex()}"


def _decode_bytea(value: object, *, column: str) -> bytes:
    """Parse a PostgREST ``bytea`` cell, or fail closed.

    Accepts ``bytes``/``bytearray`` (a client that already decoded) and the
    ``"\\x<hex>"`` text form. Anything else — a bare hex string without the prefix, a
    base64 blob, ``None`` — raises instead of being coerced: silently mis-decoding a
    nonce would turn a storage bug into an authentication failure at open time, which is
    a much harder thing to diagnose.
    """
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if not isinstance(value, str) or not value.startswith(_BYTEA_HEX_PREFIX):
        raise ConnectionStoreError(
            f"{TABLE_NAME}.{column} must be a bytea hex literal ('\\\\x…') or bytes, "
            f"got {type(value).__name__}"
        )
    try:
        return bytes.fromhex(value[len(_BYTEA_HEX_PREFIX) :])
    except ValueError:
        raise ConnectionStoreError(
            f"{TABLE_NAME}.{column} is not valid hex after the '\\\\x' prefix"
        ) from None


def _rows(response: PostgrestResponse) -> list[dict[str, object]]:
    """PostgREST responses expose their payload as ``.data``; absent means no rows."""
    data = getattr(response, "data", None)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ConnectionStoreError(
            f"expected a list of {TABLE_NAME} rows, got {type(data).__name__}"
        )
    return [row for row in data if isinstance(row, dict)]


def _row_to_connection(row: dict[str, object]) -> BrokerConnection:
    payload = dict(row)
    payload["ciphertext"] = _decode_bytea(payload.get("ciphertext"), column="ciphertext")
    payload["nonce"] = _decode_bytea(payload.get("nonce"), column="nonce")
    payload["scopes"] = tuple(payload.get("scopes") or ())
    return BrokerConnection.model_validate(payload)


def _row_to_fingerprint(row: dict[str, object]) -> ConnectionFingerprint:
    payload = dict(row)
    payload["scopes"] = tuple(payload.get("scopes") or ())
    return ConnectionFingerprint.model_validate(payload)


def _audit(event: str, **fields: object) -> None:
    """Emit one audit line built from named, non-secret fields only.

    Not routed through ``digibase.audit.redact_mapping``: that redactor is key-name based
    and does not recurse (see the warning in `research/supabase_io.py`), so relying on it
    would make safety depend on field naming. Every call site here passes ids, statuses,
    and fingerprints explicitly instead — there is no mapping in scope that could contain
    a secret to begin with.
    """
    logger.info(
        "broker_connections audit: %s %s",
        event,
        " ".join(f"{key}={value}" for key, value in fields.items()),
    )


def create_connection(
    *,
    client: SupabaseClient,
    workspace_id: UUID | str,
    broker: Broker | str,
    env: ConnectionEnv | str,
    credential: BrokerCredentialPayload,
    scopes: Sequence[str] = (),
    key: MasterKey | None = None,
) -> BrokerConnection:
    """Seal ``credential`` and insert one active `broker_connections` row.

    ``auth_kind`` and ``fingerprint`` are both derived from the credential, so neither can
    disagree with the sealed bytes. The partial unique index on
    ``(workspace_id, broker, env) WHERE status = 'active'`` is what makes a second *active*
    re-connect a conflict rather than a shadow live credential: reconnecting means revoking
    the old row and inserting a new one (revoked history may remain — DELETE is not granted),
    deliberately not an in-place credential update (the migration's trigger forbids that too).

    Returns the stored record. The plaintext ``credential`` is not retained anywhere in
    the returned value — only its ciphertext and its 8-hex fingerprint.
    """
    resolved_workspace = workspace_id if isinstance(workspace_id, UUID) else UUID(str(workspace_id))
    resolved_broker = Broker(broker)
    resolved_env = ConnectionEnv(env)
    aad = build_aad(str(resolved_workspace), resolved_broker.value, resolved_env.value)
    envelope = seal_credential(credential, aad=aad, key=key)
    display = fingerprint(credential)

    row = {
        # Client-side id so the record is fully identified before the round-trip. A retry
        # after a commit-but-lost-response collides on the partial unique
        # (workspace_id, broker, env) WHERE status = 'active' — each call mints a fresh
        # UUID, so the active triple (not the primary key) is what prevents a second live
        # credential row.
        "id": str(uuid4()),
        "workspace_id": str(resolved_workspace),
        "broker": resolved_broker.value,
        "env": resolved_env.value,
        "auth_kind": AuthKind(credential.kind).value,
        "ciphertext": _encode_bytea(envelope.ciphertext),
        "nonce": _encode_bytea(envelope.nonce),
        "key_id": envelope.key_id,
        "fingerprint": display,
        "scopes": list(scopes),
        "status": ConnectionStatus.ACTIVE.value,
    }
    returned = _rows(client.table(TABLE_NAME).insert(row).execute())
    if not returned:
        raise ConnectionStoreError(
            f"insert into {TABLE_NAME} returned no row; the client must request "
            "'Prefer: return=representation' so created_at can be read from the database "
            "clock rather than guessed"
        )
    connection = _row_to_connection(returned[0])
    _audit(
        "create",
        connection_id=connection.id,
        workspace_id=connection.workspace_id,
        broker=connection.broker.value,
        env=connection.env.value,
        auth_kind=connection.auth_kind.value,
        key_id=connection.key_id,
        fingerprint=connection.fingerprint,
    )
    return connection


def get_connection(
    *,
    client: SupabaseClient,
    workspace_id: UUID | str,
    broker: Broker | str,
    env: ConnectionEnv | str,
) -> BrokerConnection:
    """Fetch the sealed connection for one ``(workspace_id, broker, env)``.

    Returns the row whatever its status — the fail-closed check belongs to
    :func:`open_credential`, so a caller can still read and display a revoked row.
    """
    resolved_workspace = workspace_id if isinstance(workspace_id, UUID) else UUID(str(workspace_id))
    resolved_broker = Broker(broker)
    resolved_env = ConnectionEnv(env)
    response = (
        client.table(TABLE_NAME)
        .select(_FULL_COLUMNS)
        .eq("workspace_id", str(resolved_workspace))
        .eq("broker", resolved_broker.value)
        .eq("env", resolved_env.value)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    if not rows:
        raise ConnectionNotFoundError(
            f"no {TABLE_NAME} row for workspace_id={resolved_workspace} "
            f"broker={resolved_broker.value} env={resolved_env.value}"
        )
    return _row_to_connection(rows[0])


def list_connection_fingerprints(
    *,
    client: SupabaseClient,
    workspace_id: UUID | str,
) -> list[ConnectionFingerprint]:
    """List a workspace's connections in display-safe form, newest first.

    The select omits ``ciphertext``/``nonce`` entirely, so the sealed bytes never leave
    the database for this call.
    """
    resolved_workspace = workspace_id if isinstance(workspace_id, UUID) else UUID(str(workspace_id))
    response = (
        client.table(TABLE_NAME)
        .select(_FINGERPRINT_COLUMNS)
        .eq("workspace_id", str(resolved_workspace))
        .order("created_at", desc=True)
        .execute()
    )
    return [_row_to_fingerprint(row) for row in _rows(response)]


def mark_connection_used(
    *,
    client: SupabaseClient,
    connection_id: UUID,
    used_at: datetime | None = None,
) -> None:
    """Stamp ``last_used_at``. One of the three columns the migration lets us UPDATE."""
    stamp = (used_at or datetime.now(tz=UTC)).astimezone(UTC).isoformat()
    client.table(TABLE_NAME).update({"last_used_at": stamp}).eq("id", str(connection_id)).execute()


def revoke_connection(
    *,
    client: SupabaseClient,
    connection_id: UUID,
    revoked_at: datetime | None = None,
) -> BrokerConnection:
    """Mark a connection ``revoked``; idempotent, and never deletes the credential row.

    The update is guarded by ``status <> 'revoked'`` so a replay does not move
    ``revoked_at`` — the first revocation time is the one that stays on the record. When
    the guard matches nothing, the row is re-read to tell "already revoked" (returned as
    a success, since the caller's intent is satisfied) from "no such row" (raises).

    An ``expired`` row is revocable: expiry and revocation are different claims, and a
    user disconnecting an expired connection must still get a terminal ``revoked`` state.
    """
    stamp = (revoked_at or datetime.now(tz=UTC)).astimezone(UTC).isoformat()
    response = (
        client.table(TABLE_NAME)
        .update({"status": ConnectionStatus.REVOKED.value, "revoked_at": stamp})
        .eq("id", str(connection_id))
        .neq("status", ConnectionStatus.REVOKED.value)
        .execute()
    )
    rows = _rows(response)
    if rows:
        connection = _row_to_connection(rows[0])
        _audit(
            "revoke",
            connection_id=connection.id,
            workspace_id=connection.workspace_id,
            broker=connection.broker.value,
            env=connection.env.value,
            fingerprint=connection.fingerprint,
        )
        return connection

    existing = _rows(
        client.table(TABLE_NAME)
        .select(_FULL_COLUMNS)
        .eq("id", str(connection_id))
        .limit(1)
        .execute()
    )
    if not existing:
        raise ConnectionNotFoundError(f"no {TABLE_NAME} row with id={connection_id}")
    connection = _row_to_connection(existing[0])
    _audit(
        "revoke_noop",
        connection_id=connection.id,
        status=connection.status.value,
        fingerprint=connection.fingerprint,
    )
    return connection


@contextmanager
def open_credential(
    *,
    client: SupabaseClient,
    connection: BrokerConnection,
    key: MasterKey | None = None,
    touch: bool = True,
) -> Iterator[CredentialLease]:
    """Open a connection's credential for the duration of the ``with`` block.

    Fails closed before any decryption when the row is not ``active``, so revocation does
    not depend on the ciphertext becoming unreadable. With ``touch=True`` the use is
    recorded (``last_used_at``) *before* the credential is handed over, and a failure to
    record propagates: if we cannot write down that a credential was used, we do not use
    it. Callers that legitimately have no write path (a read-only diagnostic) pass
    ``touch=False`` explicitly.
    """
    if connection.status is not ConnectionStatus.ACTIVE:
        raise ConnectionRevokedError(
            f"{TABLE_NAME} row id={connection.id} is {connection.status.value}, not active; "
            f"fingerprint={connection.fingerprint} will not be unsealed"
        )
    if touch:
        mark_connection_used(client=client, connection_id=connection.id)
    with unseal_credential(connection.sealed_envelope, aad=connection.aad, key=key) as lease:
        _audit(
            "open",
            connection_id=connection.id,
            broker=connection.broker.value,
            env=connection.env.value,
            fingerprint=lease.fingerprint,
        )
        yield lease


__all__ = [
    "TABLE_NAME",
    "AuthKind",
    "Broker",
    "BrokerConnection",
    "BrokerCredentialPayload",
    "ConnectionEnv",
    "ConnectionFingerprint",
    "ConnectionNotFoundError",
    "ConnectionRevokedError",
    "ConnectionStatus",
    "ConnectionStoreError",
    "SupabaseClient",
    "create_connection",
    "get_connection",
    "list_connection_fingerprints",
    "mark_connection_used",
    "open_credential",
    "revoke_connection",
]
