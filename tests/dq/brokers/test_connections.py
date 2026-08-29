"""Contract tests for the K3 `broker_connections` store.

No live database: :class:`FakeSupabaseClient` is a small in-memory stand-in for the
PostgREST fluent chain, mirroring the fake-client pattern the atlas suite uses. What it
buys beyond "the code runs" is the ability to assert on the *requests* the store makes —
that a listing never selects the ciphertext column, that a revoke is guarded so a replay
cannot move ``revoked_at``, and that ``bytea`` values go out in Postgres' hex literal form
rather than as some other encoding the database would silently accept and mangle.
"""

from __future__ import annotations

import logging
import traceback
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from digiquant.brokers.connections import (
    TABLE_NAME,
    ApiKeyCredential,
    AuthKind,
    Broker,
    BrokerConnection,
    ConnectionEnv,
    ConnectionFingerprint,
    ConnectionNotFoundError,
    ConnectionRevokedError,
    ConnectionStatus,
    ConnectionStoreError,
    create_connection,
    get_connection,
    list_connection_fingerprints,
    mark_connection_used,
    open_credential,
    revoke_connection,
)
from digiquant.brokers.contracts import BrokerError
from digiquant.vault import (
    MASTER_KEY_BYTES,
    MasterKey,
    OAuthCredential,
    SealedEnvelope,
    build_aad,
    fingerprint,
    open_bytes,
    seal_credential,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

KEY = MasterKey(key_id="v1", material=bytes([0x11]) * MASTER_KEY_BYTES)
OTHER_KEY = MasterKey(key_id="v1", material=bytes([0x99]) * MASTER_KEY_BYTES)

WORKSPACE = UUID("11111111-1111-4111-8111-111111111111")
OTHER_WORKSPACE = UUID("22222222-2222-4222-8222-222222222222")
CREATED_AT = "2026-08-29T12:00:00+00:00"


class FakeQuery:
    """One PostgREST request under construction; records what was asked for."""

    def __init__(self, client: FakeSupabaseClient, table: str) -> None:
        self._client = client
        self._table = table
        self.operation: str | None = None
        self.selected: str | None = None
        self.payload: dict[str, Any] | None = None
        self.filters: list[tuple[str, str, Any]] = []
        # Not named `order`: that would shadow the `order()` method below.
        self.order_by: tuple[str, bool] | None = None
        self.limit_value: int | None = None

    def select(self, columns: str) -> FakeQuery:
        self.operation = "select"
        self.selected = columns
        return self

    def insert(self, row: dict[str, Any]) -> FakeQuery:
        self.operation = "insert"
        self.payload = row
        return self

    def update(self, values: dict[str, Any]) -> FakeQuery:
        self.operation = "update"
        self.payload = values
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("neq", column, value))
        return self

    def order(self, column: str, desc: bool = False) -> FakeQuery:
        self.order_by = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self.limit_value = count
        return self

    def execute(self) -> FakeResponse:
        self._client.requests.append(self)
        return FakeResponse(self._client.resolve(self))


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]] | None) -> None:
        self.data = data


class FakeSupabaseClient:
    """In-memory `broker_connections`: enough PostgREST semantics for these tests.

    Row matching honours ``eq``/``neq`` filters so the revoke guard
    (``neq("status", "revoked")``) behaves like the real thing — a replayed revoke matches
    zero rows here, exactly as it would against Postgres.
    """

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows: list[dict[str, Any]] = list(rows or [])
        self.requests: list[FakeQuery] = []

    def table(self, name: str) -> FakeQuery:
        assert name == TABLE_NAME, f"unexpected table {name!r}"
        return FakeQuery(self, name)

    def _matches(self, row: dict[str, Any], query: FakeQuery) -> bool:
        for op, column, value in query.filters:
            actual = row.get(column)
            if op == "eq" and str(actual) != str(value):
                return False
            if op == "neq" and str(actual) == str(value):
                return False
        return True

    def resolve(self, query: FakeQuery) -> list[dict[str, Any]] | None:
        if query.operation == "insert":
            assert query.payload is not None
            stored = dict(query.payload)
            stored.setdefault("created_at", CREATED_AT)
            stored.setdefault("revoked_at", None)
            stored.setdefault("last_used_at", None)
            self.rows.append(stored)
            return [dict(stored)]
        if query.operation == "update":
            assert query.payload is not None
            updated: list[dict[str, Any]] = []
            for row in self.rows:
                if self._matches(row, query):
                    row.update(query.payload)
                    updated.append(dict(row))
            return updated
        matched = [dict(row) for row in self.rows if self._matches(row, query)]
        if query.order_by is not None:
            column, desc = query.order_by
            matched.sort(key=lambda row: str(row.get(column) or ""), reverse=desc)
        if query.limit_value is not None:
            matched = matched[: query.limit_value]
        return [self._project(row, query.selected) for row in matched]

    @staticmethod
    def _project(row: dict[str, Any], selected: str | None) -> dict[str, Any]:
        """Return only the selected columns, as PostgREST does.

        Faithful projection is what makes the "a listing must not select the sealed
        columns" assertion bite end to end: if the store widened its select to include
        `ciphertext`, the column would come back here and `ConnectionFingerprint`
        (``extra="forbid"``) would refuse to build.
        """
        if selected is None:
            return row
        columns = [column.strip() for column in selected.split(",")]
        return {column: row[column] for column in columns if column in row}


def _stored_row(
    *,
    workspace_id: UUID = WORKSPACE,
    broker: str = "alpaca",
    env: str = "paper",
    status: str = "active",
    credential: ApiKeyCredential | OAuthCredential | None = None,
    key: MasterKey = KEY,
    row_id: UUID | None = None,
    revoked_at: str | None = None,
    last_used_at: str | None = None,
) -> dict[str, Any]:
    """Build a row exactly as PostgREST would return it, including bytea hex literals."""
    payload = credential or ApiKeyCredential(key_id="stored-key-id", secret="stored-secret")
    envelope = seal_credential(
        payload,
        aad=build_aad(str(workspace_id), broker, env),
        key=key,
    )
    return {
        "id": str(row_id or uuid4()),
        "workspace_id": str(workspace_id),
        "broker": broker,
        "env": env,
        "auth_kind": payload.kind,
        "ciphertext": "\\x" + envelope.ciphertext.hex(),
        "nonce": "\\x" + envelope.nonce.hex(),
        "key_id": envelope.key_id,
        "fingerprint": fingerprint(payload),
        "scopes": [],
        "status": status,
        "created_at": CREATED_AT,
        "revoked_at": revoked_at,
        "last_used_at": last_used_at,
    }


@pytest.fixture
def credential() -> ApiKeyCredential:
    return ApiKeyCredential(key_id="unit-broker-key-id", secret="unit-broker-secret")


# --- create -----------------------------------------------------------------------


def test_create_seals_the_credential_and_returns_a_fingerprint_only_record(
    credential: ApiKeyCredential,
) -> None:
    client = FakeSupabaseClient()
    connection = create_connection(
        client=client,
        workspace_id=WORKSPACE,
        broker=Broker.ALPACA,
        env=ConnectionEnv.PAPER,
        credential=credential,
        scopes=("trading",),
        key=KEY,
    )

    assert connection.status is ConnectionStatus.ACTIVE
    assert connection.auth_kind is AuthKind.API_KEY
    assert connection.fingerprint == fingerprint(credential)
    assert connection.scopes == ("trading",)
    assert connection.created_at == datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    # The stored bytes really do decrypt back to the credential under this row's AAD.
    assert (
        open_bytes(connection.sealed_envelope, aad=connection.aad, key=KEY).decode()
        == '{"key_id":"unit-broker-key-id","kind":"api_key","secret":"unit-broker-secret"}'
    )


def test_create_writes_no_plaintext_column(credential: ApiKeyCredential) -> None:
    client = FakeSupabaseClient()
    create_connection(
        client=client,
        workspace_id=WORKSPACE,
        broker="alpaca",
        env="paper",
        credential=credential,
        key=KEY,
    )
    (request,) = client.requests
    assert request.payload is not None
    rendered = repr(request.payload)
    assert credential.secret not in rendered
    assert credential.key_id not in rendered
    assert set(request.payload) == {
        "id",
        "workspace_id",
        "broker",
        "env",
        "auth_kind",
        "ciphertext",
        "nonce",
        "key_id",
        "fingerprint",
        "scopes",
        "status",
    }


def test_create_encodes_bytea_as_postgres_hex_literals(credential: ApiKeyCredential) -> None:
    """PostgREST is a JSON boundary, so bytes must go out as ``\\x<hex>``; anything else
    is either rejected or silently stored as the wrong bytes."""
    client = FakeSupabaseClient()
    create_connection(
        client=client,
        workspace_id=WORKSPACE,
        broker="alpaca",
        env="paper",
        credential=credential,
        key=KEY,
    )
    (request,) = client.requests
    assert request.payload is not None
    for column in ("ciphertext", "nonce"):
        value = request.payload[column]
        assert isinstance(value, str) and value.startswith("\\x")
        bytes.fromhex(value[2:])  # raises if the tail is not hex
    assert len(bytes.fromhex(request.payload["nonce"][2:])) == 12


def test_create_derives_auth_kind_from_the_credential_never_from_an_argument() -> None:
    client = FakeSupabaseClient()
    connection = create_connection(
        client=client,
        workspace_id=WORKSPACE,
        broker="alpaca",
        env="paper",
        credential=OAuthCredential(access_token="oauth-access"),
        key=KEY,
    )
    assert connection.auth_kind is AuthKind.OAUTH
    assert client.requests[0].payload is not None
    assert client.requests[0].payload["auth_kind"] == "oauth"


def test_create_accepts_string_identity_arguments(credential: ApiKeyCredential) -> None:
    client = FakeSupabaseClient()
    connection = create_connection(
        client=client,
        workspace_id=str(WORKSPACE),
        broker="alpaca",
        env="paper",
        credential=credential,
        key=KEY,
    )
    assert connection.workspace_id == WORKSPACE
    assert connection.broker is Broker.ALPACA


@pytest.mark.parametrize(("broker", "env"), [("robinhood", "paper"), ("alpaca", "sandbox")])
def test_create_rejects_values_outside_the_column_vocabularies(
    credential: ApiKeyCredential, broker: str, env: str
) -> None:
    client = FakeSupabaseClient()
    with pytest.raises(ValueError):
        create_connection(
            client=client,
            workspace_id=WORKSPACE,
            broker=broker,
            env=env,
            credential=credential,
            key=KEY,
        )
    assert client.requests == []


def test_create_fails_loudly_when_the_insert_echoes_no_row(credential: ApiKeyCredential) -> None:
    class SilentClient(FakeSupabaseClient):
        def resolve(self, query: FakeQuery) -> list[dict[str, Any]] | None:
            super().resolve(query)
            return []

    with pytest.raises(ConnectionStoreError, match="return=representation"):
        create_connection(
            client=SilentClient(),
            workspace_id=WORKSPACE,
            broker="alpaca",
            env="paper",
            credential=credential,
            key=KEY,
        )


# --- read -------------------------------------------------------------------------


def test_get_connection_decodes_the_sealed_columns() -> None:
    row = _stored_row()
    connection = get_connection(
        client=FakeSupabaseClient([row]),
        workspace_id=WORKSPACE,
        broker="alpaca",
        env="paper",
    )
    assert isinstance(connection, BrokerConnection)
    assert connection.ciphertext == bytes.fromhex(row["ciphertext"][2:])
    assert connection.nonce == bytes.fromhex(row["nonce"][2:])


def test_get_connection_raises_when_absent() -> None:
    with pytest.raises(ConnectionNotFoundError):
        get_connection(
            client=FakeSupabaseClient(),
            workspace_id=WORKSPACE,
            broker="alpaca",
            env="paper",
        )


def test_get_connection_scopes_the_query_to_one_row_identity() -> None:
    client = FakeSupabaseClient([_stored_row(), _stored_row(workspace_id=OTHER_WORKSPACE)])
    connection = get_connection(
        client=client, workspace_id=OTHER_WORKSPACE, broker="alpaca", env="paper"
    )
    assert connection.workspace_id == OTHER_WORKSPACE
    (request,) = client.requests
    assert ("eq", "workspace_id", str(OTHER_WORKSPACE)) in request.filters
    assert ("eq", "broker", "alpaca") in request.filters
    assert ("eq", "env", "paper") in request.filters


@pytest.mark.parametrize(
    "bad_value",
    ["deadbeef", "0x00ff", None, 17, "\\xnothex"],
    ids=["missing_prefix", "wrong_prefix", "null", "int", "bad_hex"],
)
def test_malformed_bytea_fails_closed_rather_than_being_guessed(bad_value: object) -> None:
    """A mis-decoded nonce would surface much later as an unexplained authentication
    failure, so the decode refuses anything that is not exactly the hex literal form."""
    row = _stored_row()
    row["nonce"] = bad_value
    with pytest.raises(ConnectionStoreError, match="nonce"):
        get_connection(
            client=FakeSupabaseClient([row]),
            workspace_id=WORKSPACE,
            broker="alpaca",
            env="paper",
        )


def test_non_list_response_payload_fails_closed() -> None:
    class WeirdClient(FakeSupabaseClient):
        def resolve(self, query: FakeQuery) -> Any:
            super().resolve(query)
            return {"id": "not-a-list"}

    with pytest.raises(ConnectionStoreError):
        get_connection(
            client=WeirdClient(),
            workspace_id=WORKSPACE,
            broker="alpaca",
            env="paper",
        )


# --- listing ----------------------------------------------------------------------


def test_listing_never_selects_the_sealed_columns() -> None:
    client = FakeSupabaseClient([_stored_row(), _stored_row(broker="ibkr")])
    listed = list_connection_fingerprints(client=client, workspace_id=WORKSPACE)

    assert len(listed) == 2
    (request,) = client.requests
    assert request.selected is not None
    assert "ciphertext" not in request.selected
    assert "nonce" not in request.selected
    assert "fingerprint" in request.selected


def test_listed_rows_carry_no_sealed_fields_at_all() -> None:
    client = FakeSupabaseClient([_stored_row()])
    (listed,) = list_connection_fingerprints(client=client, workspace_id=WORKSPACE)
    dumped = listed.model_dump()
    assert "ciphertext" not in dumped
    assert "nonce" not in dumped
    assert "key_id" not in dumped
    assert dumped["fingerprint"] == listed.fingerprint


def test_display_model_cannot_be_built_from_a_row_carrying_sealed_columns() -> None:
    """``extra="forbid"`` makes the display projection structurally unable to hold the
    ciphertext, so a widened select fails loudly instead of quietly returning secrets."""
    row = _stored_row()
    with pytest.raises(ValidationError, match="ciphertext"):
        ConnectionFingerprint.model_validate({**row, "scopes": ()})


def test_listing_is_scoped_to_the_workspace_and_newest_first() -> None:
    older = _stored_row()
    newer = _stored_row(broker="ibkr")
    newer["created_at"] = "2026-08-30T12:00:00+00:00"
    client = FakeSupabaseClient([older, newer, _stored_row(workspace_id=OTHER_WORKSPACE)])
    listed = list_connection_fingerprints(client=client, workspace_id=WORKSPACE)
    assert [row.broker for row in listed] == [Broker.IBKR, Broker.ALPACA]
    (request,) = client.requests
    assert request.order_by == ("created_at", True)


# --- open / fail closed -----------------------------------------------------------


def test_open_credential_yields_the_sealed_credential() -> None:
    credential = ApiKeyCredential(key_id="broker-key", secret="broker-secret")
    row = _stored_row(credential=credential)
    client = FakeSupabaseClient([row])
    connection = get_connection(client=client, workspace_id=WORKSPACE, broker="alpaca", env="paper")
    with open_credential(client=client, connection=connection, key=KEY) as lease:
        assert lease.credential == credential
        assert lease.fingerprint == connection.fingerprint


@pytest.mark.parametrize("status", ["revoked", "expired"])
def test_open_credential_fails_closed_on_a_non_active_row(status: str) -> None:
    """Revocation is effective the moment the status changes — it does not wait for the
    ciphertext to become unreadable, and no decryption is attempted."""
    row = _stored_row(
        status=status,
        revoked_at=CREATED_AT if status == "revoked" else None,
    )
    client = FakeSupabaseClient([row])
    connection = get_connection(client=client, workspace_id=WORKSPACE, broker="alpaca", env="paper")
    before = len(client.requests)
    with pytest.raises(ConnectionRevokedError, match=status):
        with open_credential(client=client, connection=connection, key=KEY):
            pass
    # No further request was issued: not even last_used_at was touched.
    assert len(client.requests) == before


def test_connection_revoked_error_is_a_broker_error() -> None:
    """So a caller catching the K1 exception family also catches this fail-closed path."""
    assert issubclass(ConnectionRevokedError, BrokerError)
    assert issubclass(ConnectionStoreError, BrokerError)


def test_open_credential_records_use_before_handing_over_the_secret() -> None:
    client = FakeSupabaseClient([_stored_row()])
    connection = get_connection(client=client, workspace_id=WORKSPACE, broker="alpaca", env="paper")
    with open_credential(client=client, connection=connection, key=KEY):
        update = client.requests[-1]
        assert update.operation == "update"
        assert update.payload is not None
        assert set(update.payload) == {"last_used_at"}


def test_open_credential_can_skip_the_touch() -> None:
    client = FakeSupabaseClient([_stored_row()])
    connection = get_connection(client=client, workspace_id=WORKSPACE, broker="alpaca", env="paper")
    before = len(client.requests)
    with open_credential(client=client, connection=connection, key=KEY, touch=False):
        pass
    assert len(client.requests) == before


def test_open_credential_refuses_another_rows_ciphertext() -> None:
    """The AAD comes from the record, so transplanting sealed bytes onto a different row
    identity yields an unopenable connection rather than a usable credential."""
    victim = _stored_row(workspace_id=WORKSPACE)
    attacker = _stored_row(workspace_id=OTHER_WORKSPACE)
    attacker["ciphertext"] = victim["ciphertext"]
    attacker["nonce"] = victim["nonce"]
    client = FakeSupabaseClient([attacker])
    connection = get_connection(
        client=client, workspace_id=OTHER_WORKSPACE, broker="alpaca", env="paper"
    )
    from digiquant.vault import EnvelopeAuthenticationError

    with pytest.raises(EnvelopeAuthenticationError):
        with open_credential(client=client, connection=connection, key=KEY):
            pass


def test_open_credential_fails_closed_under_the_wrong_master_key() -> None:
    from digiquant.vault import EnvelopeAuthenticationError

    client = FakeSupabaseClient([_stored_row()])
    connection = get_connection(client=client, workspace_id=WORKSPACE, broker="alpaca", env="paper")
    with pytest.raises(EnvelopeAuthenticationError):
        with open_credential(client=client, connection=connection, key=OTHER_KEY):
            pass


def test_connection_aad_is_derived_from_the_row() -> None:
    connection = get_connection(
        client=FakeSupabaseClient([_stored_row()]),
        workspace_id=WORKSPACE,
        broker="alpaca",
        env="paper",
    )
    assert connection.aad == f"{WORKSPACE}:alpaca:paper".encode()


def test_sealed_envelope_property_revalidates_lengths() -> None:
    from pydantic import ValidationError

    row = _stored_row()
    row["nonce"] = "\\x0011"
    connection = BrokerConnection.model_validate(
        {
            **row,
            "ciphertext": bytes.fromhex(row["ciphertext"][2:]),
            "nonce": bytes.fromhex("0011"),
            "scopes": (),
        }
    )
    with pytest.raises(ValidationError):
        _ = connection.sealed_envelope


# --- revoke -----------------------------------------------------------------------


def test_revoke_marks_the_row_and_keeps_the_credential_row_in_place() -> None:
    row = _stored_row()
    client = FakeSupabaseClient([row])
    revoked = revoke_connection(client=client, connection_id=UUID(row["id"]))

    assert revoked.status is ConnectionStatus.REVOKED
    assert revoked.revoked_at is not None
    assert client.rows[0]["status"] == "revoked"
    update = client.requests[0]
    assert update.operation == "update"
    assert update.payload is not None
    # Only lifecycle columns — the migration's column-level grant admits nothing else.
    assert set(update.payload) == {"status", "revoked_at"}


def test_revoke_is_guarded_so_a_replay_cannot_move_the_revocation_time() -> None:
    row = _stored_row()
    client = FakeSupabaseClient([row])
    first = revoke_connection(
        client=client,
        connection_id=UUID(row["id"]),
        revoked_at=datetime(2026, 8, 29, 13, 0, tzinfo=UTC),
    )
    second = revoke_connection(
        client=client,
        connection_id=UUID(row["id"]),
        revoked_at=datetime(2026, 8, 30, 13, 0, tzinfo=UTC),
    )
    assert second.revoked_at == first.revoked_at
    assert second.status is ConnectionStatus.REVOKED
    assert ("neq", "status", "revoked") in client.requests[0].filters


def test_revoking_an_expired_row_still_reaches_the_terminal_state() -> None:
    """Expiry and revocation are different claims; a user disconnecting an expired
    connection must still end up with a revoked row."""
    row = _stored_row(status="expired")
    client = FakeSupabaseClient([row])
    revoked = revoke_connection(client=client, connection_id=UUID(row["id"]))
    assert revoked.status is ConnectionStatus.REVOKED
    assert revoked.revoked_at is not None


def test_revoking_an_unknown_id_raises() -> None:
    with pytest.raises(ConnectionNotFoundError):
        revoke_connection(client=FakeSupabaseClient(), connection_id=uuid4())


def test_revoked_row_cannot_be_opened_afterwards() -> None:
    row = _stored_row()
    client = FakeSupabaseClient([row])
    revoke_connection(client=client, connection_id=UUID(row["id"]))
    connection = get_connection(client=client, workspace_id=WORKSPACE, broker="alpaca", env="paper")
    with pytest.raises(ConnectionRevokedError):
        with open_credential(client=client, connection=connection, key=KEY):
            pass


def test_mark_connection_used_normalizes_the_stamp_to_utc() -> None:
    row = _stored_row()
    client = FakeSupabaseClient([row])
    tokyo = timezone(timedelta(hours=9))
    mark_connection_used(
        client=client,
        connection_id=UUID(row["id"]),
        used_at=datetime(2026, 8, 30, 0, 0, tzinfo=tokyo),
    )
    assert client.rows[0]["last_used_at"] == "2026-08-29T15:00:00+00:00"


def test_timestamps_are_normalized_to_utc_on_read() -> None:
    row = _stored_row()
    row["created_at"] = "2026-08-29T14:00:00+02:00"
    connection = get_connection(
        client=FakeSupabaseClient([row]),
        workspace_id=WORKSPACE,
        broker="alpaca",
        env="paper",
    )
    assert connection.created_at == datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def test_naive_timestamps_are_rejected() -> None:
    from pydantic import ValidationError

    row = _stored_row()
    row["created_at"] = "2026-08-29T14:00:00"
    with pytest.raises(ValidationError):
        get_connection(
            client=FakeSupabaseClient([row]),
            workspace_id=WORKSPACE,
            broker="alpaca",
            env="paper",
        )


# --- plaintext absence across the store ------------------------------------------


def test_store_operations_never_surface_plaintext(caplog: pytest.LogCaptureFixture) -> None:
    """The store's own audit logs, records, and error paths are held to the same rule as
    the envelope: fingerprints only."""
    secret = "STORE-PLAINTEXT-9z8y7x-never-observable"
    broker_key_id = "STORE-BROKER-KEY-ID-6w5v4u"
    credential = ApiKeyCredential(key_id=broker_key_id, secret=secret)
    client = FakeSupabaseClient()
    observed: list[str] = []

    with caplog.at_level(logging.DEBUG):
        connection = create_connection(
            client=client,
            workspace_id=WORKSPACE,
            broker="alpaca",
            env="paper",
            credential=credential,
            scopes=("trading",),
            key=KEY,
        )
        observed += [repr(connection), str(connection), repr(connection.sealed_envelope)]

        fetched = get_connection(
            client=client, workspace_id=WORKSPACE, broker="alpaca", env="paper"
        )
        observed += [repr(fetched), str(fetched)]
        observed += [
            repr(row) for row in list_connection_fingerprints(client=client, workspace_id=WORKSPACE)
        ]

        with open_credential(client=client, connection=fetched, key=KEY) as lease:
            observed += [repr(lease), str(lease)]
            assert lease.credential.secret == secret

        revoked = revoke_connection(client=client, connection_id=connection.id)
        observed += [repr(revoked), str(revoked)]

        with pytest.raises(ConnectionRevokedError) as excinfo:
            with open_credential(client=client, connection=revoked, key=KEY):
                pass
        observed.append(str(excinfo.value))
        observed.append("".join(traceback.format_exception(excinfo.value)))

    for record in caplog.records:
        observed += [record.getMessage(), str(record.args)]

    haystack = "\n".join(observed)
    for leak in (secret, broker_key_id):
        assert leak not in haystack, f"{leak!r} escaped a store surface"
    # And the audit trail really did run — otherwise the assertion above is vacuous.
    audit_lines = [
        r.getMessage() for r in caplog.records if "broker_connections audit" in r.getMessage()
    ]
    assert {"create", "open", "revoke"} <= {line.split()[2] for line in audit_lines}
    assert all(connection.fingerprint in line for line in audit_lines)


def test_sealed_envelope_round_trips_through_a_stored_row() -> None:
    """End-to-end: seal, render as a PostgREST row, read it back, open it."""
    credential = OAuthCredential(
        access_token="round-trip-access", refresh_token="round-trip-refresh"
    )
    row = _stored_row(credential=credential, broker="ibkr")
    client = FakeSupabaseClient([row])
    connection = get_connection(client=client, workspace_id=WORKSPACE, broker="ibkr", env="paper")
    assert connection.sealed_envelope == SealedEnvelope(
        ciphertext=connection.ciphertext,
        nonce=connection.nonce,
        key_id=connection.key_id,
    )
    with open_credential(client=client, connection=connection, key=KEY) as lease:
        assert lease.credential == credential
