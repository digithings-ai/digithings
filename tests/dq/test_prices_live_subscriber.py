"""Guards the BROWSER SUBSCRIBER of the live equity feed — `useLivePrices` (#1807).

`digiquant/supabase/functions/prices-live/index.ts` publishes; this module guards the other
end of the wire. Until 2026-08-01 the equities lane joined the Realtime *broadcast* topic
``prices:live``. Broadcast messages are client-authored — delivery is a bare INSERT into
``realtime.messages``, ``anon`` holds INSERT on that table, and the anon key ships in
plaintext in every digiquant.io bundle — so anyone could publish quotes that arrived at this
hook indistinguishable from Finnhub's. The intended patch, migration 062, put RLS policies on
``realtime.messages``; it is UNIMPLEMENTABLE and has been deleted. Proven read-only against
the live project on 2026-08-01: that table is owned by ``supabase_realtime_admin``, a role
with zero members and no holder of admin option; our connection is ``postgres``
(``rolsuper = false``, not a member); and PostgreSQL 17.6 no longer lets CREATEROLE imply
admin over arbitrary roles, so ``CREATE POLICY`` raises ``42501 must be owner of table
messages`` for us permanently.

The hole is therefore ABANDONED, not policed: ``prices:live`` stays an open, anon-writable
broadcast topic on this project forever, harmless only because nothing subscribes to it any
more. Keeping it unsubscribed is a property of *this file*, which is why it is asserted here.
The control that replaced it lives on objects we own — ``public.prices_live`` (migration 063)
has RLS enabled with exactly one policy, ``FOR SELECT``, and no write policy at all (absent
policy = deny), and postgres_changes events are replayed from the WAL rather than accepted
from clients, so there is no path for a browser to inject one.

Why assert on source text from pytest: ``frontend/digiquant-web`` has NO test runner. Its
``package.json`` defines only dev/build/start/lint, the tree contains zero test files, and
``next.config.mjs`` sets ``eslint.ignoreDuringBuilds = true``. The deleted
``test_migration_062.py`` held ``test_subscriber_joins_a_private_channel`` — the only
assertion anywhere in this repo about ``useLivePrices.ts``. This module replaces that
coverage in the same style as ``test_prices_live_publish.py`` and
``test_prices_live_rate_guard.py``: read the TypeScript, assert on its structure.

Every failure this file guards is SILENT. Nothing throws, nothing logs, and the tape keeps
rendering lane 1's stale daily closes — which look like prices. There is no runtime signal to
regress toward, so the structure is the signal.

Both files here narrate the retired broadcast design at length, deliberately, so that nobody
"simplifies" it back into existence. Every assertion — positive and negative alike — therefore
runs against comment-stripped source: a naive substring check for "broadcast" would otherwise
be satisfied by the prose warning against it. Running the *positives* through the same
stripper is not symmetry for its own sake; it is how a regression in `_strip_comments` fails
loudly instead of quietly gutting every negative below.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIVE_DIR = _REPO_ROOT / "frontend" / "digiquant-web" / "lib" / "live"
_HOOK_TS = _LIVE_DIR / "useLivePrices.ts"
_TRANSFORMS_TS = _LIVE_DIR / "quote-transforms.ts"
_BARREL_TS = _LIVE_DIR / "index.ts"

TABLE = "prices_live"

# The transform the subscriber must feed each WAL payload through, and the two it replaced.
LIVE_TRANSFORM = "priceRowToLive"
RETIRED_TRANSFORMS = ("parseBroadcastPayload", "broadcastQuoteToLive")

# `const <name> = useId()` — the per-instance suffix, captured so the channel-topic assertion
# can demand *that* identifier rather than any interpolation at all.
_USE_ID_BINDING = re.compile(r"const\s+(?P<name>\w+)\s*=\s*useId\(\)")
_REACT_IMPORT = re.compile(r'import\s*\{(?P<names>[^}]*)\}\s*from\s*"react"')

# First argument of `.channel(`. The template-literal branch is tried first so a backticked
# topic is captured whole; the fallback captures a bare identifier or string up to the comma
# or the closing paren, which is exactly the shape this test exists to reject.
_CHANNEL_ARG = re.compile(r"\.channel\(\s*(?P<arg>`[^`]*`|[^,)]+)")

# The postgres_changes filter object. Anchored on the event-name argument rather than on
# `.on(`: the real call is `.on<Record<string, unknown>>(`, and the usual generic-tolerant
# `<[^>]*>` stops dead inside `Record<string, unknown>`.
_PG_FILTER = re.compile(r'"postgres_changes"\s*,\s*\{(?P<filter>[^{}]*)\}', re.DOTALL)


def _strip_comments(text: str) -> str:
    """Drop `/* */` blocks and `//` line comments so prose is never read as code.

    Duplicated from `test_prices_live_publish.py` rather than imported: nothing in this repo
    imports across test modules, and doing so would make these assertions depend on
    rootdir/pythonpath resolution.

    The `//` pass also truncates the `wss://` Coinbase URL, which is harmless — lane 3 is not
    under assertion here. Verified 2026-08-01 that neither file contains a `/*` or `*/` inside
    a `//` comment, which is the one input that would make the block pass over-eat.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return "\n".join(re.sub(r"//.*$", "", line) for line in without_blocks.splitlines())


def _hook_code() -> str:
    return _strip_comments(_HOOK_TS.read_text(encoding="utf-8"))


def _transforms_code() -> str:
    return _strip_comments(_TRANSFORMS_TS.read_text(encoding="utf-8"))


def test_equity_lane_subscribes_to_postgres_changes_on_public_prices_live() -> None:
    """The subscription must name the schema and the table, not just the feature.

    `postgres_changes` with a wrong or missing `table` is not an error at any layer: the join
    succeeds, the server sends nothing back, and the tape sits on lane 1's daily closes
    looking exactly like a closed market. `schema` is asserted too because Realtime defaults
    to no schema filter, and the publication carries other tables.
    """
    code = _hook_code()
    match = _PG_FILTER.search(code)
    assert match, (
        'no `.on("postgres_changes", { ... })` subscription in useLivePrices — the equity '
        "lane is not reading public.prices_live at all (#1807)"
    )
    pg_filter = match.group("filter")
    assert re.search(r'schema:\s*"public"', pg_filter), (
        'the postgres_changes filter does not pin `schema: "public"`'
    )
    # Accept the module constant or the literal, but require the constant to be bound to this
    # exact table name — a bare `table: PRICES_TABLE` proves nothing on its own.
    names_the_table = re.search(rf'table:\s*"{TABLE}"', pg_filter) or (
        re.search(r"table:\s*PRICES_TABLE", pg_filter)
        and re.search(rf'PRICES_TABLE\s*=\s*"{TABLE}"', code)
    )
    assert names_the_table, f"the postgres_changes filter does not target public.{TABLE}"


def test_the_equity_lane_never_joins_a_private_channel() -> None:
    """`private: true` is the single worst silent-degradation trap in this change.

    That flag routes the join through RLS on `realtime.messages`. There are no policies on
    that table and none can ever be created (see the module docstring: 42501, owned by a
    memberless role), so with RLS consulted every join is REFUSED. Realtime does not throw and
    the hook does not log; `setQuotes` simply never fires and the page silently decays to lane
    1's stale daily closes. It reads as "the market is closed", indefinitely.

    It is an easy flag to re-add in good faith — the retired broadcast lane genuinely needed
    it, and the comment explaining why is still in the file.
    """
    assert not re.search(r"private:\s*true", _hook_code()), (
        "`private: true` is back in useLivePrices — it only ever meant anything for RLS on "
        "`realtime.messages`, which we can never create a policy on, so every Realtime join "
        "is refused and the equity lane goes silently dark (#1807)"
    )


def test_the_forgeable_broadcast_topic_is_not_reinstated() -> None:
    """Nothing may subscribe to `prices:live` again — the topic is abandoned, not secured.

    `anon` keeps its platform INSERT grant on `realtime.messages` and we cannot revoke it, so
    that topic stays open and anon-writable on this project forever. It is harmless purely
    because no client listens. Re-adding a broadcast listener here — even alongside the table
    lane, even "just as a fallback" — restores the forgery path in full: forged quotes would
    arrive indistinguishable from Finnhub's.

    A blanket token check rather than a pair of call-shape regexes: it cannot be sidestepped
    by a generic parameter or an aliased `.on`, and it doubles as a canary on
    `_strip_comments` — both files discuss broadcast heavily in prose, so if the stripper ever
    regresses this assertion is the first to go red.
    """
    for label, code in (
        ("useLivePrices.ts", _hook_code()),
        ("quote-transforms.ts", _transforms_code()),
    ):
        assert "broadcast" not in code.lower(), (
            f"`broadcast` appears in executable code in {label} — the anon-forgeable "
            "Realtime topic must stay unsubscribed (#1807)"
        )
        assert "prices:live" not in code, (
            f"the retired `prices:live` topic name is back in {label} — it is an open, "
            "anon-writable broadcast channel and nothing may join it"
        )


def test_the_realtime_topic_is_per_hook_instance_not_a_shared_constant() -> None:
    """A shared topic string kills the equity lane for the WHOLE page, silently.

    TWO `useLivePrices` instances mount on the landing page: `LiveTickerRow` directly, and
    `DashboardPortfolioPanel` via `useLivePortfolio`. They share one singleton Supabase client,
    and `RealtimeClient.channel()` DEDUPES BY TOPIC (realtime-js 2.104.0,
    RealtimeClient.js:305-316) — the second call returns the FIRST channel instead of creating
    another. Both instances then `.on()` that one channel, but only the first `.subscribe()`
    does anything (RealtimeChannel.js:120 gates on `isClosed()`), so the join payload carries
    ONE postgres_changes filter while the client holds TWO bindings. The server's `ok` reply
    is index-matched against those bindings; the second finds no counterpart, and
    `_updatePostgresBindings` (RealtimeChannel.js:181-185) responds by calling `unsubscribe()`
    and marking the channel `errored`. Both consumers lose the lane. No exception, no console
    error — just a tape frozen on lane 1's daily closes.

    This trap is SPECIFIC to postgres_changes. Broadcast bindings carry no server-assigned id
    to match, so a shared topic was harmless on the retired lane — which is exactly why a bare
    module constant survived review until the transport moved.
    """
    code = _hook_code()

    react_import = _REACT_IMPORT.search(code)
    assert react_import, "useLivePrices no longer imports from react — retarget this test"
    assert "useId" in react_import.group("names"), (
        "`useId` is not imported from react — the Realtime topic cannot be per-instance"
    )

    binding = _USE_ID_BINDING.search(code)
    assert binding, (
        "no `const <name> = useId()` in useLivePrices — without a per-instance suffix the two "
        "landing-page hook instances collide on one topic and both lose the equity lane"
    )
    instance_id = binding.group("name")

    # Exactly one, so the assertion below cannot bind to some other, correct `.channel(` while
    # the equity lane quietly reverts to a constant.
    assert code.count(".channel(") == 1, (
        f"expected exactly one `.channel(` call in useLivePrices, found {code.count('.channel(')}"
        " — retarget this test"
    )
    channel_arg = _CHANNEL_ARG.search(code)
    assert channel_arg, "could not read the `.channel(` topic argument — retarget this test"
    topic = channel_arg.group("arg").strip()
    assert topic.startswith("`"), (
        f"the Realtime topic is `{topic}` — a bare constant. Two hook instances mount on the "
        "landing page and RealtimeClient.channel() dedupes by topic, so the second binding "
        "goes unmatched and _updatePostgresBindings unsubscribes the channel out from under "
        "BOTH of them (#1807). Interpolate the useId() instance id."
    )
    assert f"${{{instance_id}}}" in topic, (
        f"the Realtime topic does not interpolate `{instance_id}` (the useId() value): {topic}"
    )


def test_the_transform_layer_speaks_rows_and_no_longer_speaks_broadcast() -> None:
    """`priceRowToLive` replaced the two broadcast transforms; neither may linger.

    A surviving `parseBroadcastPayload` / `broadcastQuoteToLive` is a loaded gun: the parsing
    half of the forgeable path, sitting exported from the live barrel, one `.on()` away from
    being wired back up. They are dead code with a hazard attached, so their absence is
    asserted rather than left to review.

    The barrel is checked too — `lib/live/index.ts` is what the components import, and a
    re-export naming a function that no longer exists is a build break nothing in CI would
    catch until the web lane runs.
    """
    transforms = _transforms_code()
    hook = _hook_code()
    barrel = _strip_comments(_BARREL_TS.read_text(encoding="utf-8"))

    assert re.search(rf"export function {LIVE_TRANSFORM}\b", transforms), (
        f"quote-transforms.ts no longer exports `{LIVE_TRANSFORM}` — nothing turns a "
        f"public.{TABLE} WAL row into a LiveQuote"
    )
    assert LIVE_TRANSFORM in barrel, f"`{LIVE_TRANSFORM}` is not re-exported from lib/live"
    assert f"{LIVE_TRANSFORM}(" in hook, (
        f"useLivePrices does not call `{LIVE_TRANSFORM}` — the postgres_changes payload is "
        "not being transformed into a quote"
    )

    for retired in RETIRED_TRANSFORMS:
        for label, code in (
            ("quote-transforms.ts", transforms),
            ("useLivePrices.ts", hook),
            ("lib/live/index.ts", barrel),
        ):
            assert retired not in code, (
                f"`{retired}` is back in {label} — that is the parsing half of the forgeable "
                "broadcast path and it must stay deleted (#1807)"
            )
