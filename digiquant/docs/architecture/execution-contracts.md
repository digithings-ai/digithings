## execution contracts

> Split out of [digiquant/ARCHITECTURE.md](../../ARCHITECTURE.md) (DIG-3399). Prose is unchanged. Relative links were adjusted for this directory.

`digiquant/src/digiquant/brokers/contracts.py` (K0, part of the dashboard execution/tenancy
program — see `docs/superpowers/specs/2026-08-29-execution-tenancy-implementation-spec.md`
§4-K0) defines the typed venue/order/position surface every `BrokerAdapter` implementation
exchanges with a venue, replacing the previous ad hoc positional `submit_order(symbol,
side, quantity, order_type)` call. This work package is **contracts and typing only**: no
HTTP client, no broker SDK, no database access, and no venue router — a later work package
(K1 Alpaca, K2 IBKR, K4 router/sync) builds on this surface without changing it.

Operator env names live in `digiquant.dashboard.envcompat` and are all
`DIGIQUANT_*` (execution routing, overlay persist, staging JWT, research knobs);
no read-aliases remain. `DIGIQUANT_EXECUTION_ROUTING` defaults **off** — do not
enable it without an explicit human decision. `pipeline-digiquant.yml` exports
`DIGIQUANT_ATTEMPT`.

### Vocabulary and models

- `ExecutionVenue` (`StrEnum`): `paper_internal`, `alpaca_paper`, `ibkr_paper`,
  `alpaca_live`, `ibkr_live`. The `*_live` members exist so the vocabulary is complete for
  K4's venue-resolution policy; nothing in the codebase today constructs a resolver that
  reaches either one, and K4's spec binds `resolve_venue` raising on any `*_live` value as
  a test-pinned invariant.
- `BrokerOrderStatus` (`StrEnum`): `submitted`, `accepted`, `partially_filled`, `filled`,
  `canceled`, `rejected`, `expired`.
- `OrderSide` (`StrEnum`): `buy`, `sell`. `TimeInForce` (`StrEnum`): `day`, `gtc`, `opg`,
  `ioc`. `OrderType` (`StrEnum`): `market`, `limit` — v1 scope only; stop/stop-limit are
  deferred to whichever work package's behavior spec first needs them.
- `BrokerOrderRequest`: `client_order_id`, `symbol`, `side`, `quantity` XOR `notional`
  (exactly one, mirroring `RequestedTarget`'s weight/quantity XOR in
  `portfolio/models/portfolio_ledger.py`), `order_type`, `limit_price` (required iff
  `order_type` is `limit`, forbidden otherwise), `time_in_force`.
- `BrokerOrderAck`: `external_order_id`, `status`, `submitted_at` (UTC), `raw_sha256` — a
  SHA-256 hex fingerprint of the venue's raw response, never the payload itself.
- `BrokerFill`: `external_fill_id`, `symbol`, strictly-positive `quantity`/`price`,
  optional non-negative `fee`, `executed_at` (UTC). "No fill happened" is the absence of a
  row, never a zero-valued one — same invariant as `PaperExecution`.
- `BrokerPosition`: `symbol`, signed `quantity` (long positive, short negative),
  non-negative `avg_entry_price`, signed `market_value`/`unrealized_pl`.
- `BrokerAccountSnapshot`: `account_id`, signed `equity`/`cash`, non-negative
  `buying_power`, 3-letter uppercase `currency`, `as_of` (UTC).

All money/quantity fields are `Decimal` (`allow_inf_nan=False`), never `float`. Every
model is frozen with `extra="forbid"` (`BrokerContractModel`, mirroring
`PortfolioLedgerModel`), and every UTC-only datetime field is rejected if naive or offset
by anything other than +00:00 via a locally reimplemented `_reject_non_utc` (mirrors
`portfolio_ledger._reject_non_utc`; not imported, since that helper is private to its
module). `symbol` and `currency` fields are stripped and uppercased by a `mode="before"`
field validator before length/pattern validation runs.

### Widened `BrokerAdapter` protocol

`digiquant/src/digiquant/brokers/base.py`'s `runtime_checkable` `BrokerAdapter` `Protocol`
gained `get_account() -> BrokerAccountSnapshot`, `get_positions() -> list[BrokerPosition]`,
`get_order(external_order_id) -> BrokerOrderAck`, `cancel_order(external_order_id) ->
None`, and `list_fills(since: datetime) -> list[BrokerFill]`, alongside the existing
`name`/`connect`/`disconnect`. `submit_order` changed shape from the legacy positional
`submit_order(symbol, side, quantity, order_type) -> str` to `submit_order(req:
BrokerOrderRequest) -> BrokerOrderAck` — the legacy signature is deliberately not part of
this protocol.

All three stubs in `brokers/stubs.py` (`IBAdapterStub`, `AlpacaAdapterStub`,
`QuantConnectAdapterStub`) were migrated to the widened surface; every method still raises
`NotImplementedError`, so `isinstance(<stub>(), BrokerAdapter)` holds without any of them
doing real work. `digiquant/brokers/__init__.py` re-exports the contracts alongside the
protocol and stubs.

### Scope and anti-goals

No I/O, no database, no new runtime dependency, and no live-order-routing path anywhere in
this module — `ExecutionVenue` defines `*_live` members but nothing routes to them. This
work package's pre-push hook enforces a small set of forbidden method-name tokens for any
order-submission code (see `scripts/hooks/pre-push.sh`); none of those tokens appear
anywhere in `brokers/contracts.py`, `brokers/base.py`, or `brokers/stubs.py` — every method
here is named `submit_order`, `get_order`, `cancel_order`, or `list_fills`. Broker
stub/protocol coverage lives entirely in `tests/dq/brokers/test_contracts.py` — the legacy
`tests/dq/test_brokers.py` was deleted and its coverage folded in there.

### Alpaca adapter

`digiquant/src/digiquant/brokers/alpaca.py` (K1) is the first real `BrokerAdapter`
implementation: Alpaca Trading API **paper only**, via the optional
`digiquant[brokers-alpaca]` extra (`alpaca-py>=0.40,<1` — capped to the current major
because a broker SDK is a behavior-critical boundary). Auth is a tagged union
`ApiKeyAuth | OAuthAuth`; construction always passes `paper=True` to `TradingClient`, and
any non-`paper` `env` raises `LiveVenueNotAuthorizedError` (no live override in this
program yet).

Binding behavior: every submit sets Alpaca `client_order_id` from
`BrokerOrderRequest.client_order_id` and, on transport **or** rate-limit failure,
recovers via `get_order_by_client_id` before any retry — only a confirmed HTTP 404
(`BrokerOrderNotFound`) authorizes a resubmit; any other lookup failure propagates.
Notional or fractional qty requires `time_in_force=day` (local `BrokerOrderRejected`,
no HTTP); `extended_hours` is never sent; HTTP errors map to the shared exception
family in `contracts.py` (`BrokerAuthError` / `BrokerOrderNotFound` /
`BrokerOrderRejected` / `BrokerRateLimited` / `BrokerTransportError`); money/qty
parse with `Decimal(str(...))`; logs carry a 6-char sha256 fingerprint +
`X-Request-ID`, never secrets. Fills are derived from closed-order
`filled_qty`/`filled_avg_price` via REST polling (no activities helper / websocket in v1).

The package imports without the extra (`brokers/__init__.py` lazy-exports `AlpacaAdapter`;
`alpaca.py` guards the SDK import). Mocked unit tests live in
`tests/dq/brokers/test_alpaca_adapter.py`; live paper smoke is
`tests/dq/brokers/test_alpaca_integration.py` behind the `alpaca_paper` marker + env keys
(excluded from CI).

### Credential vault (K3)

`digiquant/src/digiquant/vault/envelope.py` seals broker credentials so that the
plaintext exists only inside a process, only for the duration of a `with` block, and
never in Postgres, a log record, a `repr`, or a traceback. `brokers/connections.py` is
the store that puts sealed rows in `public.broker_connections` (migration 099) through
the same Supabase client seam research uses (`dashboard/research/supabase_io.py`), and the
vault has no database import of its own — the crypto is testable without a DB and the
store is testable without a key.

**Envelope.** AES-256-GCM (`cryptography`), a fresh 96-bit random nonce per seal, and
AAD = `f"{workspace_id}:{broker}:{env}"`. The AAD is the design's load-bearing part: it
binds a ciphertext to the row that holds it, so bytes lifted from another workspace's
row — or from the same workspace's `paper` row pasted onto its `live` row — fail
authentication rather than decrypt. Nonces are never reused because they are never
derived; a seal that cannot obtain 12 fresh random bytes fails instead of falling back.

**Master key.** `DIGIQUANT_VAULT_MASTER_KEY`, base64 of exactly 32 raw bytes, read at
first use with **no default and no fallback**: a wrong length, bad base64, or missing
variable raises `VaultConfigurationError` naming the problem without echoing the value.
`DIGIQUANT_VAULT_KEY_ID` (default `v1`) is recorded on every row as `key_id` so a later
rotation can tell which rows are sealed under which key; opening a row whose `key_id`
does not match the loaded key raises `VaultKeyMismatchError` rather than attempting a
decrypt that would fail confusingly. There is no rotation implementation in K3 — only
the field that makes one possible without a schema change.

**Payloads.** Plaintext is canonical JSON (sorted keys, no spaces) of a Pydantic tagged
union with `extra="forbid"`: `OAuthCredential` (`kind="oauth"`) or `ApiKeyCredential`
(`kind="api_key"`). Validation happens *before* the seal, so a malformed credential
cannot be stored as an opaque blob that only fails at unseal time on a live path.
Unseal re-validates, because a row is untrusted input even after its tag verifies.

**Fingerprint.** First 8 hex chars of `sha256` over the secret material — the only
displayable artifact anywhere in this subsystem. It is a label, not an identity: 32 bits
collide, so nothing compares fingerprints to conclude two rows hold the same credential.

**Lease.** `unseal_credential` yields a `CredentialLease` context manager rather than
returning the credential, and the lease refuses to hand out plaintext after the block
exits (`CredentialLeaseExpiredError`). This does not "erase" the secret — CPython gives
no such guarantee, and the docstring says so instead of implying it. What it does buy is
that a caller cannot *accidentally* hold a credential past its use site, and that the
plaintext has an explicit, greppable lifetime in every caller.

**Store.** `create_connection` seals and inserts; `get_connection` / `open_credential`
read and unseal, failing closed on a revoked or non-active row
(`ConnectionRevokedError`); `revoke_connection` sets `status`/`revoked_at`;
`list_connection_fingerprints` returns a display model that carries no sealed columns at
all — it is built with `extra="forbid"` over a narrowed `select`, so a future widening of
that projection breaks a test instead of leaking ciphertext into a UI payload.
Re-connecting a broker is revoke + insert, never an update — uniqueness is a partial
unique index on `(workspace_id, broker, env) WHERE status = 'active'` so a revoked row
and a new active row can coexist (DELETE is not granted to service_role).

**Test vectors.** `tests/dq/vault/vectors.json` commits `(key, nonce, aad, plaintext,
ciphertext)` tuples plus negative cases, generated deterministically from this
implementation with synthetic keys. The K4-era Supabase Edge Function TypeScript
implementation must pass the identical suite — that file, not this prose, is the
cross-language contract. `tests/dq/vault/test_envelope.py` verifies the vectors
round-trip, and covers wrong-key, wrong-AAD, truncated-ciphertext, flipped-bit, and
key-id-mismatch failures alongside a test that captures logging across seal/unseal and
asserts no plaintext reaches any log record, `repr`, or exception message.

**Not in K3:** no key rotation, no broker adapter wiring, no Edge Function, no HTTP
surface, and nothing on a live-trading path. Migration 099 is not applied live without
the repository's human migration review gate.

### IBKR adapter

`digiquant/src/digiquant/brokers/ibkr.py` (K2) implements `BrokerAdapter` against IBKR's
Client Portal Web API. **Read-first:** `get_account` / `get_positions` use
`/portfolio/accounts`, paginated `/portfolio/{id}/positions/{page}`, `/summary`, and
`/ledger` on the SSO/live-session layer and never call `/iserver/auth/ssodh/init`.
`connect()` checks `/iserver/auth/status`; `keepalive()` is a single `POST /tickle` (no
threads — the caller owns any tickle loop). Expired sessions get one transparent re-auth,
then `BrokerAuthError`.

Order submission is implemented but locked behind `DIGIQUANT_IBKR_ORDERS=1` (default off;
`submit_order` raises `IbkrOrdersDisabledError`). When enabled, brokerage init uses
`compete=false`, surfaces competing sessions as `SessionCompetingError` without kicking the
user, resolves `conid` via `/iserver/secdef/search` (per-symbol cache), submits
`POST /iserver/account/{id}/orders`, and walks the reply chain against
`SUPPRESSIBLE_MESSAGE_IDS` (re-applied via `/iserver/questions/suppress` after every session
init). Off-allowlist prompts → `BrokerOrderRejected(question_text)`.

Pacing: monotonic-clock ≥5s spacing on `/portfolio/accounts`, `/iserver/orders`,
`/iserver/trades` — violation raises `BrokerRateLimited` (no silent sleep). Money/qty parse
as `Decimal`; logs carry response SHA-256 fingerprints only. Auth is an injected
pre-authenticated `IbkrTransport` (no OAuth signing in-tree yet). Optional extra
`brokers-ibkr = ["httpx>=0.27"]`. Operational notes: `digiquant/docs/brokers/IBKR-NOTES.md`.
Broker exceptions use the shared family in `contracts.py` (`BrokerAuthError`,
`BrokerOrderRejected`, `BrokerRateLimited`, `BrokerTransportError`); IBKR-only
`IbkrOrdersDisabledError` and `SessionCompetingError` remain in `ibkr.py`.
Tests: `tests/dq/brokers/test_ibkr_adapter.py` (mocked transport only).

### execution router + mirror

`digiquant/src/digiquant/execution/` (K4) routes approved portfolio order intents to an
external paper venue after commit / `execute_at_open`, and mirrors acks / fills / positions
append-only (D10). The internal `paper_internal` path is unchanged. Venue-session
calendar resolution for deferred execution is `execution/market_hours.py` (#3612) —
pure helpers over `trading_calendar` + `ticker_venues`; import that submodule
directly (not via package `__init__`) to avoid circular imports with `execution_io`.
Live-venue refusals in `execution/policy.py` are unchanged by the calendar gate.

**Venue resolution (`policy.py`).** `resolve_venue(workspace_id, *, active_paper_brokers)`
performs **no I/O**. House / system — `workspace_id is None` **or** the well-known
`house_workspace_id()` / `system_workspace_id()` UUIDs → always `PAPER_INTERNAL`
(hard-coded; those identities can never route externally). Kill switch
`DIGIQUANT_EXECUTION_ROUTING` defaults **off** (inverse polarity of `DIGIQUANT_PORTFOLIO_LEDGER`):
off ⇒ only `PAPER_INTERNAL` regardless of connections. With the switch on, a **tenant**
workspace with exactly one active paper `broker_connections` row maps to `ALPACA_PAPER` /
`IBKR_PAPER`; zero → `PAPER_INTERNAL`; two or more → `AmbiguousVenueError`. v1 does **not**
store an execution-policy column on `workspaces` (T0 untouched; richer policy lands with
T4). Live venue / broker tokens in `active_paper_brokers` (e.g. `"alpaca_live"`,
`ExecutionVenue.ALPACA_LIVE`) raise `LiveVenueNotAuthorizedError` on the **public** API
(not a bare `ValueError`); `_assert_not_live` remains defense-in-depth on the return path.

**Router (`router.py`) — authority boundary.** Gates evaluate first:
`workspace_id` is passed to `resolve_venue` **unchanged** (`None` / house /
system UUID ⇒ `PAPER_INTERNAL`; never substituted with
`connection.workspace_id`). `connection.env != paper` raises
`LiveVenueNotAuthorizedError` before any `submit_order`. After a non-internal
venue is resolved for a real overlay workspace, ledger reads are **threaded**
with that `workspace_id` (T4 omitted workspace ⇒ house, so overlay intents are
otherwise invisible). `_scope_ledger_rows_to_workspace` then asserts every
returned row matches the connection; a same-date pending head missing
`workspace_id` raises `ForeignWorkspaceIntentError` (scoped `eq` cannot observe
a null column, so the router does a date-scoped missing-id scan that never
submits). Foreign-workspace intents are never submitted. Builds
`BrokerOrderRequest` from a pending `OrderIntent` (`client_order_id = str(order_intent_id)`;
side from `DecisionIntent.action` via `_directions_by_order` — never from the positions
book). `NO_OP`/`REJECT` with a pending intent → `InconsistentOrderChainError`. Appends one
`broker_orders` row with deterministic id `uuid5(ns, f"{order_intent_id}:{broker}:{date}")`
— retries collide, never duplicate. `upsert` is forbidden.

**Sync (`sync.py`).** Per active connection: refresh order status (supersede chain), pull
fills since a `SyncCursor`, append `broker_executions` (`uuid5(connection_id,
external_fill_id)`), and take a positions/account snapshot. Alpaca ≤6 REST
calls/connection/cycle (`SyncBudgetExceeded`); IBKR pacing lives in the adapter (≥5s).
Credentials are unsealed only inside the caller's `open_credential` lease — sync never
sees plaintext. Unlinked (orphan) fills hold `fills_since` at the previous cursor so
exclusive-`since` adapters re-read them next cycle (`unlinked_fills_held_cursor`);
operator remedy: ensure the submit mirror exists or resolve symbol ambiguity.
Reconciliation: snapshot vs fill-implied expectation → `reconciliation_diverged` +
structured report on the snapshot row + log; **never** auto-submit corrective orders
(`SyncResult.refused_corrective_orders` is always true).

**Cron CLI (`route_cron.py`, `python -m digiquant.execution.route_cron`).**
Overlay persist writes order intents; this is the production submit seam
(`route_pending_orders` was library-only). Same eligibility as sync: Alpaca
paper OAuth only; house/system never; `env=live` refused; IBKR held; Alpaca
`api_key` held. `--check` logs `routing_enabled=true|false` and exits **2**
when store env names are missing. `--dry-run` never unseals. `--all` /
`--connection-id` with `DIGIQUANT_EXECUTION_ROUTING` off exit **3**
(`DIGIQUANT_ROUTING_DISABLED`) and do not call `submit_order`. Operator
`--connection-id` errors use the ``execution route:`` prefix (not ``execution sync:``).
`--dispatch` / `--apply` exit **4**. Kill switch still defaults **off**. Do not add
`DIGIQUANT_EXECUTION_ROUTING` to `STAGING_REQUIRED_SECRETS` (that list is
vendor EF secrets). Paper-fill remaining hop can still prove via sync of
Alpaca UI fills without this cron.

**Cron CLI (`sync_cron.py`, `python -m digiquant.execution.sync_cron`).**
Production entry that polls **Alpaca paper OAuth** connections only. House and
system workspace ids are never sync targets; `env=live` is refused; inactive
rows are dropped. IBKR paper is counted then held
(`ibkr_requires_brokerage_session`) — cron does not open a brokerage session.
Alpaca `auth_kind=api_key` is counted then held
(`alpaca_api_key_does_not_prove_oauth_hop`) — `--all` must not poll that row,
and `--connection-id` on it exits **3** with `ALPACA_API_KEY_SYNC_HELD`.
`--check` exits **2** with `DIGIQUANT_SYNC_NOT_CONFIGURED` listing missing store
env *names*. `--dry-run` prints candidate counts (`ibkr_held`,
`alpaca_api_key_held`) and does not unseal. Apply requires `--connection-id`
or `--all` (refuses implicit broker polls). Apply without an injected callback
also requires `DIGIQUANT_VAULT_MASTER_KEY` (names only on failure). Credentials
are unsealed only inside `open_credential` for Alpaca OAuth adapter
construction — `api_key` payloads are never polled. Do not run `--all` against
Observer until an Alpaca paper OAuth connection exists. The fill remaining-hop
requires a mirrored row with a symbol **and** an Alpaca paper OAuth connection.

**`execute_at_open` seam.** `resolve_execution_venue_for_run` is the only new call site;
invalid / empty `DIGIQUANT_EXECUTION_WORKSPACE_ID` warns and falls back to house
(`paper_internal`). Default (no workspace / kill switch off) stays on
`build_events_from_paper_fills`. Migration 102 + `tests/dq/dashboard/execution/`.

