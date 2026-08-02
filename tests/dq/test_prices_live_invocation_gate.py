"""Guards the `prices-live` edge function's invocation gate (#1756).

The function is a Deno edge function, so it cannot be imported and exercised from
pytest — there is no `deno` in CI and no Deno lane in `.github/workflows/`. Rather
than ship a Deno test nothing runs, this module audits the source the way
`tests/scripts/test_check_frontend_canon.py` audits CSS: structurally, asserting the
properties that make the gate load-bearing rather than merely present.

Why a gate at all: `verify_jwt` proves the caller holds *a* project key, and the anon
key ships in every browser bundle. Before #1756 the only gates were the Finnhub key
and `if (!force && !isExtendedUsMarketHours(at))`, so during the ~60h/week market
window a plain `{}` POST with the public anon key ran the identical Finnhub fetch loop
and produced a service-role-authored broadcast. `force` widened that to 24/7; it was
never the vulnerability, which is why gating only `force` would fix nothing.

The ordering assertions are the point. A gate placed after the cheaper gates leaks a
state oracle and, worse, is trivially re-orderable by a later edit that looks harmless.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FUNCTION_DIR = _REPO_ROOT / "digiquant" / "supabase" / "functions" / "prices-live"
_INDEX_TS = _FUNCTION_DIR / "index.ts"
_README = _REPO_ROOT / "digiquant" / "supabase" / "README.md"

SECRET_ENV = "PRICES_LIVE_INVOKE_SECRET"
SECRET_HEADER = "x-prices-live-secret"


def _source() -> str:
    return _INDEX_TS.read_text(encoding="utf-8")


def _handler_body(source: str) -> str:
    """The `Deno.serve(...)` request handler only — module scope is not the gate."""
    start = source.index("Deno.serve(")
    return source[start:]


def _strip_comments(body: str) -> str:
    """Drop `//` line comments so prose about a gate is never mistaken for the gate.

    Without this, deleting the gate but leaving its (extensive) explanatory comment
    behind would keep every substring assertion below green.
    """
    return "\n".join(re.sub(r"//.*$", "", line) for line in body.splitlines())


def test_index_ts_exists() -> None:
    assert _INDEX_TS.is_file(), f"missing edge function source: {_INDEX_TS}"


def test_gate_reads_the_secret_env_and_header() -> None:
    source = _source()
    code = _strip_comments(_handler_body(source))
    # Accept either an inline read or the module constant, but require the constant to
    # actually be bound to this env var name — a bare substring would survive being
    # mentioned only inside a log message.
    reads_env = f'Deno.env.get("{SECRET_ENV}")' in code or (
        "Deno.env.get(INVOKE_SECRET_ENV)" in code
        and f'INVOKE_SECRET_ENV = "{SECRET_ENV}"' in source
    )
    assert reads_env, f"handler never reads {SECRET_ENV} — there is no invocation gate"
    assert f'INVOKE_SECRET_HEADER = "{SECRET_HEADER}"' in source, (
        f"the {SECRET_HEADER} header constant is not defined"
    )
    assert "req.headers.get(" in code, "handler never inspects request headers"


def test_gate_precedes_every_other_gate_and_the_fetch_loop() -> None:
    """The authorization check must come first, not merely exist.

    Anything ordered before it either burns quota for an unauthorized caller or tells
    that caller whether the key is set / the market is open.
    """
    code = _strip_comments(_handler_body(_source()))

    # Anchor on the gate's own constant, not on a generic `req.headers.get(`. If some
    # later edit adds an unrelated header read (CORS preflight, request id, trace
    # header) above the gate, a generic anchor would bind to *that* and keep this test
    # green while the secret check had moved below the fetch loop.
    assert code.count("INVOKE_SECRET_HEADER") == 1, (
        "expected exactly one header read for the invoke secret"
    )
    gate = code.index("INVOKE_SECRET_HEADER")
    # `.json()` inside the handler is only ever the request-body parse; `res.json()`
    # lives in fetchQuote, which is module scope and therefore not in `code`.
    body_parse = re.search(r"\.json\(\)", code)
    assert body_parse, "handler no longer parses a request body — update this assertion"
    later = {
        "Finnhub key gate": code.index('Deno.env.get("FINNHUB_API_KEY")'),
        "request body parse": body_parse.start(),
        "market-hours gate": code.index("isExtendedUsMarketHours(at)"),
        "Finnhub fetch loop": code.index("fetchQuote("),
        "service-role client": code.index("createClient("),
        # Retargeted, not relaxed (#1807). This entry used to anchor on `channel.send(`.
        # The publish path is now an upsert into `public.prices_live` — the broadcast topic
        # was forgeable by any anon-key holder and migration 062 could not fix it. The
        # ordering claim is unchanged and if anything stronger: `service_role` bypasses RLS,
        # so this gate is all that stands between an unauthorized caller and a write to a
        # table the whole site reads. A stale anchor here would raise ValueError from
        # `.index`, not fail an assertion — retarget it, never drop it.
        "prices_live upsert": code.index(".upsert("),
    }
    for name, position in later.items():
        assert gate < position, f"invocation gate runs AFTER the {name} — reorder it first"


def test_unauthorized_request_returns_before_any_response_body_about_state() -> None:
    """The 503 and 401 must be the handler's first two returns.

    If any `return json(...)` precedes them, an unauthorized caller can distinguish
    dormant / market-closed / configured states — an oracle the gate exists to close.
    """
    code = _strip_comments(_handler_body(_source()))
    returns = [m.start() for m in re.finditer(r"return json\(", code)]
    assert len(returns) >= 3, "expected at least the 503, the 401, and one success return"

    first_two = code[returns[0] : returns[2]]
    assert "503" in first_two, "the fail-closed 503 is not one of the first two returns"
    assert "401" in first_two, "the unauthorized 401 is not one of the first two returns"


def test_gate_fails_closed_when_the_secret_is_unset() -> None:
    """An unset secret must refuse the request, never wave it through."""
    code = _strip_comments(_handler_body(_source()))
    unset_branch = re.search(
        r"if \(!expectedSecret\) \{(.*?)\n  \}",
        code,
        re.DOTALL,
    )
    assert unset_branch, "no explicit `if (!expectedSecret)` fail-closed branch"
    assert "return json(" in unset_branch.group(1), "the unset-secret branch does not return"
    assert "503" in unset_branch.group(1), "the unset-secret branch should return 503"
    # A default value would convert fail-closed into fail-open with a guessable secret.
    assert not re.search(rf'Deno\.env\.get\("{SECRET_ENV}"\)\s*(\?\?|\|\|)', code), (
        f"{SECRET_ENV} has a fallback default — that is a fall-open path"
    )


def test_secret_comparison_is_constant_time() -> None:
    """A bare `===` short-circuits on the first differing byte and leaks length."""
    source = _source()
    assert "secretMatches" in source, "no dedicated secret-comparison helper"
    assert 'crypto.subtle.digest("SHA-256"' in source, (
        "secret comparison should digest both sides to a fixed width before comparing"
    )
    code = _strip_comments(source)
    assert not re.search(r"(===|!==)\s*expectedSecret", code), (
        "expectedSecret is compared with a short-circuiting equality operator"
    )
    assert not re.search(r"expectedSecret\s*(===|!==)", code), (
        "expectedSecret is compared with a short-circuiting equality operator"
    )


def test_docs_tell_operators_to_send_the_header() -> None:
    """The realistic regression: the gate ships, the runbook doesn't, the feed goes dark.

    Both pg_cron jobs and the smoke-test curl must carry the header, or a human
    following this README deploys the gate and 401s the live feed.
    """
    readme = _README.read_text(encoding="utf-8")
    post_blocks = readme.count("net.http_post(")
    assert post_blocks >= 2, "expected both the day and late cron snippets"
    assert readme.count(SECRET_HEADER) >= post_blocks + 1, (
        f"every net.http_post snippet plus the curl example must send {SECRET_HEADER}; "
        f"found {readme.count(SECRET_HEADER)} mentions for {post_blocks} post blocks"
    )
    assert SECRET_ENV in readme, f"README never names the {SECRET_ENV} secret"


def test_docs_no_longer_claim_the_function_is_dormant() -> None:
    """Verified live 2026-08-01: FINNHUB_API_KEY is set and both crons are active.

    `net._http_response` id 1360 returned
    `{"market":"open","forced":false,"symbols":17,"quoted":17,"broadcast":"ok"}`.
    Any doc still saying "dormant until FINNHUB_API_KEY is set" is false and was the
    reason this exposure read as harmless.
    """
    stale = re.compile(r"dormant until|does not exist yet|DORMANT BY DESIGN", re.IGNORECASE)
    for path in (
        _README,
        _INDEX_TS,
        _REPO_ROOT / "digiquant" / "ARCHITECTURE.md",
        _REPO_ROOT / "digiquant" / "supabase" / "SCHEMA.md",
    ):
        text = path.read_text(encoding="utf-8")
        assert not stale.search(text), (
            f"{path.relative_to(_REPO_ROOT)} still describes prices-live as dormant"
        )
