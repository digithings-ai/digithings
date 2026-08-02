"""Guards the `prices-live` publish path — the table, not the Realtime channel (#1807).

Until 2026-08-01 this edge function fanned each run out as one message on the Realtime
*broadcast* topic ``prices:live``. Supabase grants ``anon`` INSERT on ``realtime.messages``
and the anon key ships in plaintext in every digiquant.io bundle, so anyone who opened the
site's JS could publish **forged quotes** onto the feed without touching the function or
holding any private credential.

The intended fix, migration 062, put RLS policies on ``realtime.messages``. It cannot be
applied — proven read-only against the live project on 2026-08-01: that table is owned by
``supabase_realtime_admin``, a role with zero members and no holder of admin option; our
connection is ``postgres`` (``rolsuper = false``, not a member); and PostgreSQL 17.6 no
longer lets CREATEROLE imply admin over arbitrary roles, so ``CREATE POLICY`` raises
``42501 must be owner of table messages``. Only Supabase platform staff could clear that.

So the transport moved onto objects we own: ``public.prices_live`` (migration 063), RLS
enabled, one SELECT policy, and deliberately **no** write policy. Clients cannot write the
table, and postgres_changes payloads are replayed from the WAL rather than accepted from
clients — which is what makes forgery structurally impossible rather than merely forbidden.

Why assert on source text at all: there is no ``deno`` in CI and no Deno lane in
``.github/workflows/``, so nothing anywhere type-checks, lints or executes this file. A
misspelled column, a swapped ``q.d``/``q.dp``, or a broadcast quietly restored by a future
editor would all ship green. This module audits the source the way
``test_prices_live_invocation_gate.py`` audits the gate: structurally, on the properties
that make the fix load-bearing rather than merely present.

Every negative assertion runs against comment-stripped source. The file's header comment is
*required* to narrate this incident so nobody "simplifies" the channel back into existence;
prose about a broadcast must never be mistaken for a broadcast.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INDEX_TS = _REPO_ROOT / "digiquant" / "supabase" / "functions" / "prices-live" / "index.ts"

TABLE = "prices_live"

# The row literal, from `const rows` to the `.upsert(` it feeds. Scoping the column checks to
# this span is what makes a bare `ticker,` an unambiguous anchor.
_ROW_BLOCK = re.compile(r"const rows\b(?P<block>.*?)\.upsert\(", re.DOTALL)

# Each column of `public.prices_live` paired with the expression that must fill it.
# postgres_changes ships the row verbatim, so a renamed column breaks no build — it blanks a
# field in the browser. `change` is Finnhub `d` and `change_pct` is Finnhub `dp`: adjacent,
# similarly named, trivially swappable, and therefore asserted one by one rather than by a
# generic "the upsert has some fields in it".
COLUMN_SOURCES = {
    # Anchored to a whole line: `ticker` is shorthand for `ticker: ticker`, and a loose
    # substring would bind to the `([ticker, q])` destructuring instead — leaving the test
    # green with no primary key in the row at all.
    "ticker": r"^\s*ticker,\s*$",
    "price": r"price:\s*q\.c\b",
    "change": r"change:\s*q\.d\b",
    "change_pct": r"change_pct:\s*q\.dp\b",
    "quoted_at": r"quoted_at:\s*quotedAtIso\(",
    "updated_at": r"updated_at:\s*at\.toISOString\(\)",
}


def _source() -> str:
    return _INDEX_TS.read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    """Drop `/* */` blocks and `//` line comments so prose is never read as code.

    Duplicated from `test_prices_live_invocation_gate.py` rather than imported: nothing in
    this repo imports across test modules, and doing so would make these assertions depend on
    rootdir/pythonpath resolution. Note the block pass, which that module does not need and
    this one does — the JSDoc on `quotedAtIso` discusses the old broadcast path by name.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return "\n".join(re.sub(r"//.*$", "", line) for line in without_blocks.splitlines())


def _code() -> str:
    return _strip_comments(_source())


def test_the_realtime_broadcast_publish_path_is_gone() -> None:
    """No channel, no send, no broadcast envelope — the forgeable transport must stay dead.

    `anon` holds INSERT on `realtime.messages` and cannot be stripped of it by any migration
    we are permitted to apply, so a restored broadcast is a restored forgery. This asserts on
    call tokens, never on the word "broadcast": the header comment has to keep explaining the
    incident, and extending that prose must not turn this test red.
    """
    code = _code()
    for token in ("channel.send(", ".channel(", "removeChannel("):
        assert token not in code, (
            f"`{token}` is back in prices-live — that republishes quotes on a Realtime "
            "channel anon can forge onto (#1807). The table is the fix; do not restore it."
        )
    assert not re.search(r'type:\s*["\']broadcast["\']', code), (
        "a broadcast message envelope is back in prices-live (#1807)"
    )
    assert not re.search(r"private:\s*true", code), (
        "the `private: true` channel flag survived the move off broadcast — it only ever "
        "meant anything for `realtime.messages` RLS, which migration 062 could not create"
    )


def test_quotes_are_upserted_into_prices_live_on_ticker() -> None:
    """The write must be an UPSERT keyed on the primary key, not a plain insert.

    `ticker` is the primary key of `public.prices_live`, so an insert raises 23505 on the
    second run of every ticker's life — one minute after launch.
    """
    code = _code()
    assert f'from("{TABLE}")' in code, f"prices-live never writes public.{TABLE}"
    assert ".upsert(" in code, "prices-live does not upsert — a plain insert conflicts on ticker"
    assert re.search(r'onConflict:\s*["\']ticker["\']', code), (
        'the upsert does not declare `onConflict: "ticker"`'
    )
    # `ignoreDuplicates: true` turns DO UPDATE into DO NOTHING: every ticker would freeze at
    # the first price ever written for it, forever, with a healthy-looking "ok" in the log.
    assert not re.search(r"ignoreDuplicates:\s*true", code), (
        "ignoreDuplicates: true makes the upsert DO NOTHING — prices would never update"
    )


def test_every_prices_live_column_is_populated_from_the_right_finnhub_field() -> None:
    """`d` and `dp` are one character apart and neither is type-distinguishable.

    Nothing type-checks this file, so a swap between `change` and `change_pct` ships green
    and surfaces only as a percentage rendered as dollars on the digiquant.io landing page.
    """
    match = _ROW_BLOCK.search(_code())
    assert match, "no `const rows ... .upsert(` block — retarget these column assertions"
    block = match.group("block")
    for column, pattern in COLUMN_SOURCES.items():
        assert re.search(pattern, block, re.MULTILINE), (
            f"the prices_live row does not populate `{column}` (expected /{pattern}/)"
        )


def test_quoted_at_converts_unix_seconds_to_milliseconds() -> None:
    """Finnhub `t` is unix SECONDS; `Date` takes milliseconds. The 1000x is the whole bug.

    Neither direction throws and neither fails a type check: forget the factor and every
    quote is filed in January 1970; divide instead and it lands past the year 50000. The
    browser renders whatever it is handed, so nothing anywhere reports an error.
    """
    code = _code()
    assert re.search(r"new Date\([^)]*\*\s*1000[^)]*\)", code), (
        "no `new Date(<unix seconds> * 1000)` conversion — quoted_at will be ~1970"
    )
    assert not re.search(r"new Date\([^)]*/\s*1000", code), (
        "quoted_at DIVIDES by 1000 — Finnhub `t` is already seconds, so this lands in 50000+"
    )
    assert "toISOString()" in code, "quoted_at is not serialized as an ISO 8601 timestamp"


def test_a_missing_quote_timestamp_cannot_abort_the_run() -> None:
    """`new Date(NaN).toISOString()` throws RangeError — a failure mode this path introduces.

    The broadcast payload serialized `t` as-is, so a missing or malformed Finnhub timestamp
    was inert. Multiplied into a `Date` it aborts the whole handler instead, discarding up to
    40 good prices over one bad field, and it would recur every minute for as long as Finnhub
    returned that shape. `quoted_at` is NOT NULL, so the guard needs a fallback value rather
    than an early return.
    """
    guard = re.search(r"function quotedAtIso\((?P<body>.*?)\n\}", _code(), re.DOTALL)
    assert guard, "no `quotedAtIso` helper — the unix-seconds conversion is unguarded"
    body = guard.group("body")
    assert "Number.isFinite" in body, "quotedAtIso does not reject a non-finite `t`"
    assert "fallback" in body, "quotedAtIso has no fallback for a missing `t`"


def test_the_invocation_gate_still_precedes_the_write() -> None:
    """`service_role` bypasses RLS, so the gate is the only thing guarding the table.

    The no-write-policy design stops *clients* forging quotes; it does nothing about a caller
    who can make this function write on their behalf. An unauthorized invocation must return
    before the upsert — an index comparison, because "the gate exists somewhere in the file"
    is not the property that matters.
    """
    source = _source()
    code = _strip_comments(source[source.index("Deno.serve(") :])
    assert code.count("INVOKE_SECRET_HEADER") == 1, (
        "expected exactly one header read for the invoke secret"
    )
    assert code.index("INVOKE_SECRET_HEADER") < code.index(".upsert("), (
        "the invocation gate runs AFTER the prices_live upsert — an unauthorized caller can "
        "drive a service-role write to the table the whole site reads"
    )


def test_the_response_reports_the_publish_outcome_verbatim() -> None:
    """The cron log is the only diagnostic surface a scheduled run has.

    `published` replaced `broadcast` and keeps its "ok" | <error string> shape deliberately.
    Collapse it to a boolean and the expected first-deploy failure — PostgREST answering
    `PGRST205 Could not find the table 'public.prices_live' in the schema cache` when the
    function ships ahead of migration 063 — becomes an unexplained `false` in
    `net._http_response`.
    """
    code = _code()
    assert re.search(r"\bpublished\b", code), "the response no longer reports a publish outcome"
    assert '"skipped (no quotes)"' in code, (
        "the skip marker is gone — a run that quoted nothing must say so, not report `ok`"
    )
    assert re.search(r"published\s*=\s*error\s*\?\s*error\.message", code), (
        "the upsert error is not surfaced verbatim in `published`"
    )
    assert 'published !== "ok" && quoted > 0' in code, (
        "a failed write with quotes in hand is no longer logged as an error"
    )
    # The old field name must not linger in the response object; cron log greps key off it.
    assert not re.search(r"^\s*broadcast,\s*$", code, re.MULTILINE), (
        "the response still emits a `broadcast` field"
    )
