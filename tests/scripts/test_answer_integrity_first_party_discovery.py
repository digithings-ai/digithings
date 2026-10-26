"""The first-party discovery contract for the answer-integrity check (DIG-5148).

This file is the EM's failing test. It is committed on the leaf's branch before
the implementation starts and the leaf may not edit it. It pins five behaviours,
and each one is a fact measured against the surface the check is being pointed
at, not a preference:

1. a first-party page yields the embed origin and the tenant host;
2. the probes go to the origin's answer path with ``X-Embed-Host``, ``Origin``
   and ``Referer`` naming the first-party host, and with no
   ``X-Embed-Token`` at all;
3. the iframe ``src`` query string never reaches the answer path;
4. a page with no recognisable embed markup is a discovery failure — exit 2,
   never 0 and never 1;
5. the client-style discovery (``embedUrl`` plus a depth-1 ``token`` out of the
   RSC payload) still works exactly as it does today.

Why the shapes differ. The client surface publishes a React Server Component
payload carrying ``embedUrl`` and ``token``; our own page publishes an
``<iframe src="{embedOrigin}/embed?host={host}&layout=page&...">`` and no token
at all. A first-party tenant is authorised by ``hostTenantAuthorized`` in
``apps/digichat/src/lib/embed-chat-tenant.ts`` when the selected host *and* the
browser-attested request origin are both first-party
(``apps/digichat/src/lib/embed-first-party.ts``), so presenting a token is not
merely unnecessary — an empty or placeholder token is a different request from
the one a browser on that page makes, and this test refuses it.

Why the user agent is asserted here. Our own Cloudflare zone answers urllib's
default agent with ``403`` and ``error code: 1010`` on every path of the site,
discovery and answer path alike. That is a permanent exit 2, never a green run.
The house agent is the constant ``PROBE_USER_AGENT`` in
``apps/digithings-cron/src/probe.ts``. It is a transport detail and it moves no
exit code, which is exactly why it has to be pinned: nothing else would notice
its loss until the check had been blind for a day.

The network is mocked at the one seam (``http_request``); nothing here touches a
real host, and no answer is ever written to disk.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "datatap_answer_integrity_check.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "datatap_answer_integrity_check_first_party", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()

# Every test below replaces the seam and the surface has to be left as it was
# found, or a later test in the session inherits a fake instead of the code.
_REAL_HTTP_REQUEST = mod.http_request


@pytest.fixture(autouse=True)
def _restore_the_http_request_seam() -> None:
    yield
    mod.http_request = _REAL_HTTP_REQUEST


MONITOR_TOKEN_ENV_VAR = "DATATAP_ANSWER_CHECK_MONITOR_TOKEN"
EMBED_HOSTS_ENV_VAR = "ANSWER_CHECK_EMBED_HOSTS"
TARGET_ENV_VARS = ("ANSWER_CHECK_DISCOVERY_URL", "ANSWER_CHECK_EMBED_HOST")

# Spelled out here rather than imported from the module: the value is what the
# zone allowlists, so the test pins the value and not whatever the script
# happens to hold. Same reasoning as the environment variable names above.
HOUSE_USER_AGENT = "digithings-site-smoke/1.0 (+https://github.com/digithings-ai/digithings)"

# The page and the embed target are separate things on a first-party surface.
# They are deliberately on different hosts so that a reader which quietly keeps
# the page's host cannot pass: the origin and the tenant host must both come out
# of the iframe ``src``.
SITE = "https://site.example.test"
PAGE_URL = f"{SITE}/chat/"
EMBED_ORIGIN = "https://embed.example.test"
TENANT_HOST = "tenant.example.test"

IFRAME_SRC = f"{EMBED_ORIGIN}/embed?host={TENANT_HOST}&layout=page&theme=light&wide=1"
FIRST_PARTY_HTML = (
    "<!DOCTYPE html><html><body>"
    '<iframe id="dc-digichat-frame" title="digichat" '
    f'src="{IFRAME_SRC.replace("&", "&amp;")}" class="dc-chat-frame" '
    'allow="clipboard-write"></iframe>'
    "</body></html>"
)

# A page with no embed markup at all, and a page whose one iframe is somebody
# else's. Neither names an embed origin or a tenant host, so neither is a
# surface this check can probe.
NO_EMBED_MARKUP_HTML = (
    "<!DOCTYPE html><html><head><title>digithings</title></head>"
    "<body><main><h1>Build with us</h1></main></body></html>"
)
UNRELATED_IFRAME_HTML = (
    "<!DOCTYPE html><html><body>"
    '<iframe src="https://forms.example.test/survey?utm_source=docs"></iframe>'
    "</body></html>"
)

# The client-style surface, kept neutral so this file carries no new client
# literal: the page is one host and the embed app (which holds the token in its
# RSC payload) is another, exactly as the live client shape is.
CLIENT_PAGE_URL = "https://client-page.example.test/chat"
CLIENT_EMBED_ORIGIN = "https://embed-app.example.test"
CLIENT_EMBED_HOST = "embed-app.example.test"
CLIENT_TOKEN = "t" * 48


@pytest.fixture(autouse=True)
def _a_pinned_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Both hosts the fixtures put on the wire are in the allowlist, so a run in
    # this suite is a run with the allowlist configured. A developer shell may
    # hold a different value; this one is pinned rather than inherited.
    monkeypatch.delenv(MONITOR_TOKEN_ENV_VAR, raising=False)
    for name in TARGET_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        EMBED_HOSTS_ENV_VAR,
        ",".join(("embed.example.test", "embed-app.example.test")),
    )


def _sse(*frames: dict) -> str:
    """Build an AI SDK v7 SSE body. `text-delta` frames are concatenated."""
    return "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames)


# A correct refusal: the shape the check exists to read, and the shape a real
# answer has when there is nothing to leak.
REFUSAL = "I don't have access to customer records, so I can't look up an account id or owner."


def _ok(content_type: str, body: str) -> object:
    return mod.HttpResponse(status=200, content_type=content_type, body=body)


def _rsc_page(embed_base: str) -> str:
    """The client payload: an ``embedUrl`` and its own depth-1 ``token``."""
    return (
        "<!DOCTYPE html><html><body><script>self.__next_f.push("
        '[1,"{\\"embedUrl\\":\\"' + embed_base + '/embed\\",\\"token\\":\\"'
        + CLIENT_TOKEN
        + '\\"}"]'
        "</script></body></html>"
    )


class FakeHttp:
    """Records every request and replays a scripted response per URL."""

    def __init__(self, responses: dict[str, object]):
        self.responses = responses
        self.calls: list[dict] = []

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers or {}), "body": body}
        )
        for pattern, response in self.responses.items():
            if re.search(pattern, url):
                return response
        raise AssertionError(f"unexpected request: {method} {url}")

    def posts(self) -> list[dict]:
        return [call for call in self.calls if call["method"] == "POST"]

    def gets(self) -> list[dict]:
        return [call for call in self.calls if call["method"] == "GET"]


def _header(headers: dict, name: str) -> str | None:
    """One header value, matched without regard to case.

    Header names are case-insensitive on the wire, and the dict the probe builds
    is the dict the seam receives, so a test that matched exact keys would fail
    on a spelling rather than on a behaviour.
    """
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _run(responses: dict, argv: list[str]) -> tuple[int, FakeHttp]:
    fake = FakeHttp(responses)
    mod.http_request = fake  # the single network seam
    return mod.main(argv), fake


def _answer(text: str) -> str:
    """A complete, well-formed 200 stream whose answer is exactly `text`."""
    return _sse(
        {"type": "start"},
        {"type": "text-delta", "delta": text},
        {"type": "finish"},
    )


def _first_party_responses(html: str = FIRST_PARTY_HTML) -> dict:
    return {
        re.escape(PAGE_URL) + "$": _ok("text/html; charset=utf-8", html),
        re.escape(EMBED_ORIGIN) + "/api/chat$": _ok("text/event-stream", _answer(REFUSAL)),
    }


# --------------------------------------------------------------------------
# 1. A first-party page yields the embed origin and the tenant host.
# --------------------------------------------------------------------------


def test_a_first_party_page_yields_the_embed_origin_and_the_tenant_host() -> None:
    code, fake = _run(_first_party_responses(), ["--discovery-url", PAGE_URL])

    assert code == mod.OK == 0, "a first-party page with clean answers is a pass"

    # The origin comes from the iframe src, and the answer path is built on it.
    # The page's own host is a different host, so keeping it here would show.
    assert {call["url"] for call in fake.posts()} == {f"{EMBED_ORIGIN}/api/chat"}

    # The tenant key comes from the src's `host` parameter — not from the page
    # host, and not from a default.
    for call in fake.posts():
        assert _header(call["headers"], "X-Embed-Host") == TENANT_HOST

    # Reading our own page is a request to our own zone, so it carries the
    # house agent too. Without it the discovery answers 403 and the run can
    # never be anything but exit 2.
    discovery = fake.gets()
    assert len(discovery) == 1
    assert _header(discovery[0]["headers"], "User-Agent") == HOUSE_USER_AGENT


# --------------------------------------------------------------------------
# 2. The probe presents the first-party host pair and no token.
# --------------------------------------------------------------------------


def test_the_probe_presents_the_first_party_host_pair_and_no_token() -> None:
    code, fake = _run(_first_party_responses(), ["--discovery-url", PAGE_URL])
    assert code == mod.OK

    chats = fake.posts()
    assert len(chats) == 2, "both probes must run; a skipped probe is not a pass"
    for call in chats:
        headers = call["headers"]
        assert _header(headers, "X-Embed-Host") == TENANT_HOST
        assert _header(headers, "Origin") == f"https://{TENANT_HOST}"
        assert _header(headers, "Referer") == PAGE_URL

        # Absent, not empty and not a placeholder. A tokenless tenant is
        # authorised by the host plus the browser-attested origin; sending an
        # empty or invented token would be a different request from the one a
        # browser on this page makes.
        assert not any(key.lower() == "x-embed-token" for key in headers), (
            "a first-party tenant must carry no X-Embed-Token header at all"
        )

        assert _header(headers, "User-Agent") == HOUSE_USER_AGENT


# --------------------------------------------------------------------------
# 3. The iframe src query string never reaches the answer path.
# --------------------------------------------------------------------------


def test_the_iframe_query_string_never_reaches_the_answer_path() -> None:
    # The production src carries the page's whole presentation state — layout,
    # theme, welcome text, suggestions — and none of it is part of the answer
    # path. Cutting a suffix off the string would append "/api/chat" inside the
    # query and reach nothing.
    src = (
        f"{EMBED_ORIGIN}/embed?host={TENANT_HOST}&layout=page&theme=light&wide=1"
        "&welcome=Ask+about+digithings"
        "&suggestions=What+is+digigraph%3F%7CHow+do+I+run+the+stack+locally%3F"
    )
    html = (
        "<!DOCTYPE html><html><body>"
        f'<iframe id="dc-digichat-frame" src="{src.replace("&", "&amp;")}"></iframe>'
        "</body></html>"
    )

    code, fake = _run(_first_party_responses(html), ["--discovery-url", PAGE_URL])
    assert code == mod.OK

    chats = fake.posts()
    assert len(chats) == 2
    for call in chats:
        parts = urlsplit(call["url"])
        assert parts.scheme == "https"
        assert parts.netloc == "embed.example.test"
        assert parts.path == "/api/chat"
        assert parts.query == ""
        assert parts.fragment == ""
        for leaked in ("?", "host=", "layout=", "theme=", "wide=", "welcome=", "suggestions="):
            assert leaked not in call["url"], f"{leaked!r} leaked from the iframe src"


# --------------------------------------------------------------------------
# 4. A page with no embed markup is a discovery failure, never a pass.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "html",
    [NO_EMBED_MARKUP_HTML, UNRELATED_IFRAME_HTML],
    ids=["no-iframe", "somebody-elses-iframe"],
)
def test_a_page_with_no_embed_markup_exits_2_and_never_reports_a_pass(
    html: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, fake = _run(
        {re.escape(PAGE_URL) + "$": _ok("text/html; charset=utf-8", html)},
        ["--discovery-url", PAGE_URL],
    )

    assert code == mod.COULD_NOT_RUN == 2
    assert fake.posts() == [], "no answer path is known, so nothing is probed"
    out = capsys.readouterr().out
    assert "COULD NOT RUN" in out
    assert "PASS" not in out, "a discovery failure must never read as a pass"


# --------------------------------------------------------------------------
# 5. The client-style discovery still works unchanged.
# --------------------------------------------------------------------------


def test_the_client_style_discovery_still_works_unchanged() -> None:
    page = _rsc_page(CLIENT_EMBED_ORIGIN)

    # The reader's return value is the interface the rest of the check and the
    # client deployment depend on, so it is pinned directly as well as through
    # a run.
    assert mod.discover_embed_target(page) == mod.EmbedTarget(
        embed_url=f"{CLIENT_EMBED_ORIGIN}/embed", token=CLIENT_TOKEN
    )
    assert (
        mod.discover_embed_target(page).api_chat_url
        == f"{CLIENT_EMBED_ORIGIN}/api/chat"
    )

    responses = {
        re.escape(CLIENT_PAGE_URL) + "$": _ok("text/html; charset=utf-8", page),
        re.escape(CLIENT_EMBED_ORIGIN) + "/api/chat$": _ok(
            "text/event-stream", _answer(REFUSAL)
        ),
    }
    code, fake = _run(
        responses,
        ["--discovery-url", CLIENT_PAGE_URL, "--embed-host", CLIENT_EMBED_HOST],
    )
    assert code == mod.OK

    chats = fake.posts()
    assert len(chats) == 2
    for call in chats:
        headers = call["headers"]
        assert call["url"] == f"{CLIENT_EMBED_ORIGIN}/api/chat"
        assert _header(headers, "X-Embed-Token") == CLIENT_TOKEN
        assert _header(headers, "X-Embed-Host") == CLIENT_EMBED_HOST
        assert _header(headers, "Origin") == f"https://{CLIENT_EMBED_HOST}"
        assert _header(headers, "Referer") == CLIENT_PAGE_URL
