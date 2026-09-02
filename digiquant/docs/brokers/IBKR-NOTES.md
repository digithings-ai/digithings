# IBKR Web API — operational notes (K2)

Operational companion to `digiquant.brokers.ibkr.IbkrAdapter`. Binding ground truth lives
in `docs/superpowers/specs/2026-08-29-kairos-tenancy-implementation-spec.md` §7; this note
captures the session model, onboarding path, and pacing rules the adapter implements.

## Product path vs dev path

| Path | Status | Use |
|------|--------|-----|
| **OAuth 1.0a vendor onboarding** | Required for any multi-user SaaS product | Compliance questionnaire, legal agreement, RSA keys, consumer key. IBKR-side ~3–5 weeks (often longer). Scope the initial application to **include trading** even though v1 ships read-first — a later scope change is a second compliance pass. |
| Self-service OAuth 1.0a (user generates own keys) | Gray zone ("FA/Institutional only") | **Dev / paper testing only.** Never a product dependency. |
| Client Portal Gateway (self-hosted Java + 2FA) | Rejected for hosted SaaS UX | Acceptable only for a future self-host tier. |
| OAuth 2.0 | Enterprise / institutional, no retail timeline | Keep the auth layer swappable; do not wait on it. |

**Production auth wiring is intentionally out of K2.** `IbkrAdapter` takes an injected
pre-authenticated `IbkrTransport` (live-session cookies / bearer material already
attached). The adapter never performs OAuth 1.0a signing. Wire signing + token exchange
when vendor onboarding completes (K3 credential vault + T3 Brokers settings).

K2 deliberately uses a **thin hand-rolled HTTP client surface** (`IbkrTransport` protocol)
rather than depending on `ibind`. Rationale: read-first scope does not need OAuth signing
or ibind's session helpers yet; fewer moving parts; optional extra `brokers-ibkr` reserves
`httpx` for a future concrete transport factory without forcing it on every install.

## Session model (three layers)

```
Access token (long-lived OAuth)
        │
        ▼
Live session token (~24h, DH handshake)  ← connect() verifies via /iserver/auth/status
        │                                   keepalive() = POST /tickle  (~60s cadence)
        │                                   idle timeout ~5–6 min without tickle
        ▼
Brokerage session (/iserver/auth/ssodh/init)  ← ONLY on the flagged order path
                                                compete=false by default
```

### Binding rules implemented in the adapter

1. **Read path never opens a brokerage session.** `get_account` / `get_positions` use
   `/portfolio/accounts`, `/portfolio/{id}/positions/{page}`, `/portfolio/{id}/summary`,
   `/portfolio/{id}/ledger`. Unit tests assert the mock transport never saw `ssodh/init`
   on reads.
2. **`connect()`** = auth status + live-session establishment. **`keepalive()`** =
   one `POST /tickle`. **No threads inside the adapter** — the caller (K4 sync) owns the
   tickle loop.
3. **Expired session** → exactly one transparent re-auth attempt, then `BrokerAuthError`.
4. **Order path** only when `DIGIQUANT_IBKR_ORDERS=1` (default off). Brokerage init uses
   `compete=false`. A competing response raises `SessionCompetingError` and sets
   `adapter.session_competing` — it never kicks the user's own TWS/mobile login.
5. **Reply/confirmation chain:** after every brokerage session init, re-apply
   `POST /iserver/questions/suppress` with the hard-coded allowlist in
   `SUPPRESSIBLE_MESSAGE_IDS`. Runtime prompts are confirmed via
   `POST /iserver/reply/{id}` only when every `messageIds` entry is on that allowlist;
   anything else → `BrokerOrderRejected(question_text)`.

## Dedicated second-username advice

IBKR's `compete` flag decides whether a new brokerage session displaces an existing
TWS / Client Portal / mobile login for the **same username**. For a hosted product:

- Prefer a **dedicated API / second username** on the account (IBKR supports additional
  users) so the sync/order worker never contends with the client's interactive session.
- Always init with `compete=false`. Surface "session competing" as connection status
  (`SessionCompetingError` / `session_competing`) — never silently kick the user.
- Document this choice in the Brokers settings UX (T3) when IBKR connect ships.

## Paper account setup (dev target)

- One paper account per approved (funded, Pro) live account; **separate username**.
- ~$1M simulated buying power; Web API works with "minimal differences"; fills are
  top-of-book only.
- Market-data subscriptions can be shared from the live user.
- Develop K2 against paper with self-service creds; do not treat that credential path
  as shippable product auth.

## Pacing table

Design budget: **≤10 req/s per username**. Per-endpoint spacing the adapter enforces:

| Endpoint family | Minimum spacing | Adapter behavior on violation |
|-----------------|-----------------|-------------------------------|
| `/portfolio/accounts` | 1 req / 5s | raise `BrokerRateLimited` |
| `/iserver/orders` (and order submit paths matching the marker) | 1 req / 5s | raise `BrokerRateLimited` |
| `/iserver/trades` | 1 req / 5s | raise `BrokerRateLimited` |
| `/pa/*` (performance/attribution) | 1 req / 15 min | not called by K2 |
| Global | ≤10 req/s | caller budget (K4); 429 → `BrokerRateLimited` |

Pacing uses `time.monotonic` (injectable). **Raise, do not sleep** — so K4 can schedule
spacing deliberately and unit tests stay deterministic without fake clocks for waits.

## Feature flag

```bash
# default — read path only; submit_order raises IbkrOrdersDisabledError
unset DIGIQUANT_IBKR_ORDERS

# enable the implemented order path (still requires human gate + vendor onboarding)
export DIGIQUANT_IBKR_ORDERS=1
```

## Out of scope here

Websocket topics (`sor` / `str` / `spl`), Flex Web Service fallback (optional K2b),
credential storage (K3), venue routing (K4), OAuth signing UX, live `*_LIVE` routing.
