"""Guards the `prices-live` rate guard — an ATOMIC LEASE CLAIM, not an invocation secret.

REPLACES ``test_prices_live_invocation_gate.py``, which is deleted rather than amended.
Every property that module asserted — ``secretMatches``, the ``x-prices-live-secret`` header,
the fail-closed 503, "the gate runs first" — describes a control that no longer exists.

WHY THE SECRET WENT AWAY. ``verify_jwt: true`` is not authorization: it proves the caller
holds *a* project key, and the anon key ships in plaintext in every digiquant.io bundle. So
anyone can invoke this function, and the only harm available to them is burning Finnhub's
free tier (60 calls/min) out from under the legitimate 60 s pg_cron job. That is a RATE
problem, not an IDENTITY problem. #1756 answered it with a shared secret; a secret is an
operational credential to store, rotate and lose, and it bounds *who* invokes rather than
*how often* a fetch happens. The replacement makes an unauthorized invocation worthless
instead of forbidden: the caller still gets a 200, it just does not fetch anything.

WHY THE OBVIOUS GUARD WOULD BE WORSE THAN NOTHING — the whole point of this module.
``SELECT max(updated_at) FROM prices_live; if younger than N seconds, skip`` is READ-THEN-ACT.
``updated_at`` is written by the upsert AFTER the fetch loop, and that loop is 40 symbols ×
150 ms of deliberate stagger — roughly SIX SECONDS. For those six seconds every concurrent
invocation reads the same stale timestamp, every one of them passes the freshness check, and
every one of them fetches. Ten parallel requests is ~400 Finnhub calls in six seconds: zero
protection against the only attacker that matters, while looking like a rate limit in review.
A session advisory lock is not a substitute either — PostgREST hands out a fresh session per
RPC call, so the lock releases long before the six-second fetch it would need to cover.

The guard therefore has to be ONE conditional UPDATE that reports whether this caller won
(migration 064's ``public.claim_prices_live_refresh``). Concurrent callers block on the lease
row's lock, then re-evaluate the WHERE clause against the committed new ``claimed_at`` under
READ COMMITTED and match zero rows. Exactly one winner per window, whatever the arrival
pattern. ``test_no_read_then_act_freshness_residue`` is the assertion that keeps a
well-meaning "simpler" rewrite from putting the race back.

Why assert on source text at all: there is no ``deno`` in CI and no Deno lane in
``.github/workflows/``, so nothing anywhere type-checks, lints or executes this file. Same
pattern as ``test_prices_live_publish.py``.

EVERY NEGATIVE ASSERTION RUNS ON COMMENT-STRIPPED SOURCE, and here that cuts the opposite way
from usual. The edge function's header is *required* to keep naming ``x-prices-live-secret``
and quoting ``SELECT max(updated_at) FROM prices_live`` so that nobody reintroduces either;
prose about a withdrawn control must never be mistaken for the control.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INDEX_TS = _REPO_ROOT / "digiquant" / "supabase" / "functions" / "prices-live" / "index.ts"

# The cross-file contract with migration 064. A rename on either side is a PostgREST
# `PGRST202 Could not find the function` on every run — which fails closed, i.e. the feed
# goes dark silently rather than loudly.
CLAIM_RPC = "claim_prices_live_refresh"
CLAIM_ARG = "min_age_seconds"

# Finnhub's free tier. Not a tunable: it is the number the rate invariant is measured against.
FINNHUB_CALLS_PER_MINUTE = 60

# pg_cron fires `prices-live` on this period, so the lease window must be shorter than it.
CRON_PERIOD_SECONDS = 60

_RPC_CALL = re.compile(rf"\.rpc\(\s*[\"']{CLAIM_RPC}[\"']")
_RETURN_JSON = re.compile(r"return json\(")

# Withdrawn with #1756's secret. Each of these surviving in executable code means some part of
# the credential came back — and a half-restored secret gate fails closed on the live cron.
WITHDRAWN_SECRET_TOKENS = (
    "secretMatches",
    "x-prices-live-secret",
    "PRICES_LIVE_INVOKE_SECRET",
    "INVOKE_SECRET_ENV",
    "INVOKE_SECRET_HEADER",
    "expectedSecret",
)


def _source() -> str:
    assert _INDEX_TS.is_file(), f"missing edge function source: {_INDEX_TS}"
    return _INDEX_TS.read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    """Drop `/* */` blocks and `//` line comments so prose is never read as code.

    Duplicated from `test_prices_live_publish.py` rather than imported: nothing in this repo
    imports across test modules, and doing so would make these assertions depend on
    rootdir/pythonpath resolution.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return "\n".join(re.sub(r"//.*$", "", line) for line in without_blocks.splitlines())


def _code() -> str:
    """Whole module, comments stripped — module-scope constants live out here."""
    return _strip_comments(_source())


def _handler() -> str:
    """The `Deno.serve(...)` request handler only; module scope is not the guard.

    Scoping matters for the ordering assertions: `fetchQuote(` and `isExtendedUsMarketHours(`
    are both *defined* above the handler, so a whole-file index would compare against the
    definition site instead of the call site.
    """
    source = _source()
    return _strip_comments(source[source.index("Deno.serve(") :])


def _const(name: str) -> int:
    """Read a module-scope numeric `const` out of the source.

    Anchored on `const <name> =` in comment-stripped source, because the file header narrates
    the rate arithmetic in prose — `MIN_REFRESH_SECONDS = 50` and `MAX_SYMBOLS × (60/50)` both
    appear inside `//` comments, ahead of the declarations. A looser regex would happily read
    the invariant off the paragraph that claims it holds.
    """
    match = re.search(rf"^\s*const\s+{name}\s*=\s*(\d+)\s*;", _code(), re.MULTILINE)
    assert match, f"no module-scope `const {name} = <int>;` in {_INDEX_TS.name}"
    return int(match.group(1))


def _rpc_start() -> int:
    """Offset of the single claim RPC call inside the handler."""
    handler = _handler()
    calls = list(_RPC_CALL.finditer(handler))
    assert len(calls) == 1, (
        f'expected exactly one `.rpc("{CLAIM_RPC}")` call in the handler, found '
        f"{len(calls)} — two claims per run would consume two lease windows, and the second "
        "would always lose"
    )
    return calls[0].start()


def _claim_decision() -> str:
    """The claim's decision logic: from the RPC call to the start of the skip return.

    Deliberately excludes the skip response body. Scoping this way is what lets
    `test_force_cannot_bypass_the_claim` assert on the *condition* without going red because
    somebody added `forced: force` to the skipped payload for the cron log.
    """
    handler = _handler()
    start = _rpc_start()
    nxt = _RETURN_JSON.search(handler, start)
    assert nxt, "no `return json(` after the claim — a losing caller falls through and fetches"
    return handler[start : nxt.start()]


def test_index_ts_exists() -> None:
    assert _INDEX_TS.is_file(), f"missing edge function source: {_INDEX_TS}"


def test_the_guard_is_an_atomic_claim_rpc() -> None:
    """One RPC, awaited, carrying the window — and a skip return before any fetch.

    The RPC boundary is what makes the guard atomic: the claim is a single UPDATE executed
    server-side, so "read the lease" and "take the lease" are one statement that other callers
    block on. Anything the edge function could assemble from separate round trips is not.
    """
    handler = _handler()
    start = _rpc_start()

    assert re.search(rf"{CLAIM_ARG}:\s*MIN_REFRESH_SECONDS", handler), (
        f"the claim does not pass MIN_REFRESH_SECONDS as `{CLAIM_ARG}` — migration 064 names "
        f"that parameter, and PostgREST resolves overloads by argument name, so a mismatch is "
        "PGRST202 on every single run"
    )
    assert re.search(r"await\s+\w+(?:\.\w+)*\.rpc\(", handler), (
        "the claim RPC is not awaited; an unawaited builder never executes, so `data` is a "
        "PostgrestFilterBuilder, the guard fails closed forever and the feed goes dark"
    )

    fetch = handler.index("fetchQuote(")
    skip = _RETURN_JSON.search(handler, start)
    assert skip and skip.start() < fetch, (
        "there is no `return json(` between the claim and the Finnhub fetch loop — losing the "
        "claim has to end the request, not merely be recorded"
    )
    # The skip must precede the SYMBOL QUERY too, not just the fetch. Pinning only the fetch
    # leaves room to move the early return below the `public_portfolio_positions` read, which
    # would let every losing caller — i.e. every request an attacker sends after the first in
    # a window — still drive a service-role query. Cheap per call, unbounded in aggregate, and
    # invisible: all the other assertions here stay green.
    symbol_query = handler.index('from("public_portfolio_positions")')
    assert skip.start() < symbol_query, (
        "the not-claimed return sits BELOW the public_portfolio_positions read, so a caller "
        "that lost the claim still drives a service-role query before bailing out"
    )
    assert "skipped" in handler[skip.start() : fetch], (
        "the not-claimed response has no `skipped` key; pg_cron logs land in "
        "`net._http_response` and a run that fetched must be distinguishable from one that "
        "did not"
    )


def test_no_read_then_act_freshness_residue() -> None:
    """The race this design exists to close, asserted as an absence.

    A `SELECT max(updated_at) FROM prices_live` freshness check is not a weaker version of the
    claim, it is a non-guard. `updated_at` is written AFTER the fetch loop — 40 symbols × 150 ms
    stagger, so ~6 s after the check that reads it. Every invocation arriving inside that
    window reads the same stale timestamp, all of them pass, all of them fetch: ten parallel
    requests is ~400 Finnhub calls in six seconds, against a 60/min tier. The failure is
    invisible in a sequential test and invisible in review, which is why it is pinned here.

    Comment-stripped on purpose: the edge function header quotes the rejected query verbatim so
    the next reader knows not to write it, and that prose must not trip this test.
    """
    code = _code()
    handler = _handler()

    assert not re.search(r"max\(\s*updated_at", code, re.IGNORECASE), (
        "a `max(updated_at)` freshness query is back — that is read-then-act and it protects "
        "nothing against concurrent invocations"
    )
    assert not re.search(r"order\(\s*[\"'][^\"']*updated_at", code, re.IGNORECASE), (
        "the handler orders by `updated_at` — a freshest-row lookup is the same read-then-act "
        "race by another name"
    )
    assert not re.search(r"select\(\s*[\"'][^\"']*updated_at", code, re.IGNORECASE), (
        "the handler SELECTs `updated_at`; the lease claim is the only freshness authority"
    )

    # `.select(` is legitimate here — the symbol set comes from `public_portfolio_positions`.
    # What must never appear is a read of the feed table or the lease table used as the guard,
    # so the check is scoped per `from(...)` target rather than banning `.select(` outright.
    for table in ("prices_live", "prices_live_lease"):
        for match in re.finditer(rf"from\(\s*[\"']{table}[\"']\s*\)", handler):
            tail = handler[match.end() : match.end() + 200]
            assert ".select(" not in tail, (
                f"the handler SELECTs from `{table}` — reading the lease or the feed and then "
                "deciding is exactly the six-second race the atomic claim replaces. Call "
                f"`{CLAIM_RPC}` instead; it is one UPDATE and it reports its own winner."
            )


def test_the_claim_precedes_the_symbol_query_and_the_fetch() -> None:
    """Ordering, by index — "the claim exists somewhere in the file" is not the property.

    A losing caller must not even read `public_portfolio_positions`, let alone reach Finnhub.
    The claim does sit *after* the market-hours gate, deliberately: a run that was going to
    return `{"market": "closed"}` anyway must not consume a lease window and starve the next
    real one.
    """
    handler = _handler()
    claim = _rpc_start()

    market_hours = handler.index("isExtendedUsMarketHours(at)")
    assert market_hours < claim, (
        "the claim now runs BEFORE the market-hours gate, so every closed-market invocation "
        "burns a lease window and the first in-hours cron run finds nothing to claim"
    )

    later = {
        "portfolio-ticker query": handler.index('from("public_portfolio_positions")'),
        "Finnhub fetch loop": handler.index("fetchQuote("),
        "prices_live upsert": handler.index(".upsert("),
    }
    for name, position in later.items():
        assert claim < position, (
            f"the atomic claim runs AFTER the {name}. Everything downstream of the claim is "
            "work an unauthorized caller can make this function do for free — reorder it above."
        )


@pytest.mark.parametrize("token", WITHDRAWN_SECRET_TOKENS)
def test_the_invocation_secret_gate_is_gone(token: str) -> None:
    """The secret is withdrawn, not softened; half of it left behind is worse than all of it.

    Asserted on comment-stripped source. The header still names `x-prices-live-secret` and
    `PRICES_LIVE_INVOKE_SECRET` on purpose — the removal is a decision that needs recording,
    and the next reader has to be able to find out why the credential in the README's rollout
    section no longer exists.
    """
    assert token not in _code(), (
        f"`{token}` is back in executable code. #1756's shared secret was withdrawn on "
        "purpose: it is a credential to store, rotate and lose, and it bounded who invoked "
        "rather than how often a fetch happens. The lease claim is the control now."
    )


def test_no_fail_closed_503_branch_survives() -> None:
    """The 503 belonged to "the secret is unset"; there is no secret to be unset.

    Left in place it would refuse every invocation the moment an env var nobody sets any more
    is absent — a permanently dark feed with a plausible-looking log line.

    Scoped to the handler and word-bounded rather than a bare `"401" in source`: these are
    three-digit runs, and an unanchored whole-file substring is one incidental literal — a
    timestamp, a byte count, an issue number — away from failing for no reason.
    """
    handler = _handler()
    assert not re.search(r"\b503\b", handler), (
        "a 503 branch survives the secret's removal; nothing in this function is "
        "unconfigurable any more except the Supabase env, which returns 500"
    )
    assert not re.search(r"\b401\b", handler), (
        "a 401 branch survives; there is no caller identity to reject — an unauthorized "
        "invocation gets a 200 that fetched nothing, which is the point of the redesign"
    )


def test_the_claim_fails_closed() -> None:
    """An error, a throw, and a non-`true` result must all mean NOT claimed.

    Fail-closed is what makes the deploy order safe in either direction: ship this function
    before migration 064 and PostgREST answers `PGRST202 Could not find the function`, so the
    run fetches NOTHING. Fail open and the same missing migration would fetch on *every*
    invocation from every anon-key holder — the exact state the guard was added to end.
    """
    handler = _handler()
    start = _rpc_start()
    decision = _claim_decision()

    # An explicit branch, not merely the token `error` somewhere in the span — `console.error`
    # in the catch block would satisfy that and prove nothing. `if (error)` / `!error &&` are
    # the two shapes that actually consult it.
    assert re.search(r"if\s*\(\s*!?\s*\w*[Ee]rror\w*\s*\)", decision) or re.search(
        r"!\s*\w*[Ee]rror\w*\s*&&", decision
    ), (
        "the claim's `error` is never branched on. Leaning on `data === true` alone happens to "
        "fail closed today because PostgREST nulls `data` on error — but then the "
        "expected-and-diagnosable case, migration 064 not yet applied, is indistinguishable "
        "from `false` (someone else holds the window) in the cron log, and a permanently dark "
        "feed looks exactly like a permanently busy one."
    )
    assert "try" in handler[:start][-400:], (
        "the claim RPC is not inside a `try`; postgrest-js can throw on transport failure and "
        "an unhandled throw 500s the handler instead of skipping"
    )
    assert "catch" in decision, (
        "nothing catches a throw from the claim RPC between the call and the skip return"
    )
    assert "=== true" in decision, (
        "the claim result is not compared against `true`. `data` is untyped across the "
        "PostgREST boundary: `null`, `{}` and a builder object are all non-`true` values that "
        "a truthiness test would read as a won claim."
    )
    for truthy in (r"if\s*\(\s*data\s*\)", r"!!\s*data", r"Boolean\(\s*data\s*\)"):
        assert not re.search(truthy, decision), (
            f"the claim result is tested for truthiness (/{truthy}/) instead of `=== true`; "
            "any object PostgREST hands back would pass"
        )
    assert not re.search(r"data\s*!==\s*false", decision), (
        "`data !== false` treats `null` and an error-shaped payload as a won claim"
    )

    # Fail-closed by construction, in either accepted shape: a flag that starts false, or a
    # skip test that demands `true` rather than merely not-false.
    defaults_false = re.search(r"\b(?:let|var)\s+\w+\s*=\s*false\s*;", handler[:start])
    demands_true = re.search(r"!==\s*true", handler[start:]) or re.search(
        r"if\s*\(\s*!\w+\s*\)", handler[start:]
    )
    assert defaults_false or demands_true, (
        "the guard has no fail-closed default: neither a boolean initialised to `false` before "
        "the RPC nor a skip test that requires the claim to be exactly `true`"
    )


def test_force_cannot_bypass_the_claim() -> None:
    """`force: true` overrides the market-hours gate and NOTHING else. Accepted trade.

    This is the one thing the redesign makes materially worse and it is not an oversight to
    "fix" later: a forced ops smoke test inside MIN_REFRESH_SECONDS of any other run returns
    `{"skipped": "not claimed"}` and fetches nothing. A `force` that skipped the claim would
    hand every anon-key holder the unbounded-fetch path straight back, since `force` arrives in
    a request body that anyone holding the published anon key can send.
    """
    handler = _handler()
    market_hours = handler.index("isExtendedUsMarketHours(at)")

    assert re.search(r"!force\s*&&\s*!isExtendedUsMarketHours\(at\)", handler), (
        "the market-hours gate no longer reads `!force && !isExtendedUsMarketHours(at)` — "
        "retarget this test rather than dropping it, `force` must still override that gate"
    )
    between = handler[market_hours : _rpc_start()]
    assert "force" not in between, (
        "`force` is consulted between the market-hours gate and the claim — the only way it "
        "can appear there is as a condition that skips or weakens the claim"
    )
    assert "force" not in _claim_decision(), (
        "`force` appears in the claim's decision logic. Forced or not, a caller who loses the "
        'lease must skip; otherwise `{"force": true}` is an unmetered fetch button that '
        "ships in every browser bundle."
    )


def test_the_finnhub_rate_invariant_holds() -> None:
    """(floor(60 / MIN_REFRESH_SECONDS) + 1) × MAX_SYMBOLS ≤ 60 — Finnhub's free-tier ceiling.

    Note the `+ 1`, and do NOT "simplify" this to `60 / MIN_REFRESH_SECONDS`. That intuitive
    form UNDERSTATES the ceiling and is how this shipped wrong the first time: at
    MIN_REFRESH_SECONDS = 50 it computes 1.2 windows/min and blesses 48 calls/min, but claims
    at t=0 and t=50 BOTH sit inside the sliding window [0, 60]. The true count of points that
    fit in a 60 s window at spacing ≥ T is floor(60/T) + 1 — two, not 1.2 — so the real
    ceiling was 80 calls/min against a 60/min tier. The weaker form passed, which is exactly
    why it is dangerous: it is a test that certifies the bug.

    Both numbers are parsed out of the TypeScript rather than restated here, because the
    failure this catches is somebody raising MAX_SYMBOLS in a change about coverage and never
    thinking about quota. The arithmetic is a guarantee rather than a sequential best case
    *only because* the claim is atomic — at most one caller wins each window.

    Exceeding it does not fail loudly. Finnhub answers 429 for the remainder of the minute, so
    the tail of every symbol list silently stops updating — alphabetically, which is why nobody
    notices until someone asks why the feed always drops the same tickers.
    """
    max_symbols = _const("MAX_SYMBOLS")
    min_refresh = _const("MIN_REFRESH_SECONDS")

    # Worst case, adversarially timed: a claim at t=0 and another the instant the window
    # reopens. Integer floor, then +1 for the boundary claim.
    claims_per_minute = 60 // min_refresh + 1
    calls_per_minute = claims_per_minute * max_symbols
    assert calls_per_minute <= FINNHUB_CALLS_PER_MINUTE, (
        f"MIN_REFRESH_SECONDS={min_refresh} admits {claims_per_minute} claims in a sliding "
        f"60s window; × MAX_SYMBOLS={max_symbols} = {calls_per_minute} Finnhub calls/min, "
        f"over the {FINNHUB_CALLS_PER_MINUTE}/min free tier. Lower MAX_SYMBOLS or raise "
        "MIN_REFRESH_SECONDS — the two constants are one decision, not two."
    )


def test_min_refresh_seconds_leaves_the_sixty_second_cron_room() -> None:
    """The guard must not starve the caller it exists to protect.

    pg_cron fires every 60 s and its firing time drifts by seconds. At
    MIN_REFRESH_SECONDS ≥ 60 a cron run arriving 59.6 s after the last one loses its own
    claim and skips, so the feed updates every other minute at best — a self-inflicted
    outage that looks exactly like Finnhub throttling. 50 s leaves 10 s of jitter margin.
    """
    min_refresh = _const("MIN_REFRESH_SECONDS")
    assert min_refresh < CRON_PERIOD_SECONDS, (
        f"MIN_REFRESH_SECONDS={min_refresh} is not shorter than the {CRON_PERIOD_SECONDS}s "
        "pg_cron period, so the scheduled run loses its own claim to jitter"
    )
    assert min_refresh >= 1, (
        f"MIN_REFRESH_SECONDS={min_refresh} — migration 064 raises on anything below 1, and a "
        "0 would disable the rate guard silently rather than loudly"
    )
