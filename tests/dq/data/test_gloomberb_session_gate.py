"""The secret gate that decides whether Gloomberb session tools are advertised (#2752).

Chris, 10 Oct 2026: the Gloomberb session cookie is the deployer's own secret,
from their own Gloomberb account. digithings can only hold one long enough to
check it. So a tool may be advertised only when a cookie is configured *and*
that cookie is accepted by api.gloom.sh.

These tests pin the four acceptance cases (no secret, invalid secret, valid
secret, never logged) plus the two properties the implementation rests on: the
no-secret path costs **zero** HTTP, and one TTL window costs exactly **one**
probe. Both are checked with a counted fake client, so a gate that quietly
started calling out to the network on every list would go red here rather than
in a deployer's latency budget.
"""

from __future__ import annotations

import logging

import pytest
from digiquant.data.gloomberb import session_gate
from digiquant.data.gloomberb.client import (
    DEFAULT_CACHE_TTL_SECONDS,
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    SessionCheck,
    session_cache_fingerprint,
)

pytestmark = pytest.mark.unit

_FAKE_COOKIE = "fake-session-cookie-value-not-a-real-secret"


class _FakeClient:
    """Stands in for GloomberbClient; records every build and every probe."""

    builds: list[dict[str, object]] = []
    probes: list[str | None] = []
    verdict: SessionCheck | None = None
    raises: BaseException | None = None

    def __init__(self, **kwargs: object) -> None:
        type(self).builds.append(dict(kwargs))

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def check_session(self) -> SessionCheck:
        type(self).probes.append(type(self).verdict.code if type(self).verdict else "unset")
        if type(self).raises is not None:
            raise type(self).raises
        assert type(self).verdict is not None
        return type(self).verdict


@pytest.fixture(autouse=True)
def _clean_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with an empty verdict cache and no inherited env."""
    for name in (GLOOMBERB_ENABLED_ENV, GLOOMBERB_SESSION_COOKIE_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(session_gate, "_clock", None)
    monkeypatch.setattr(session_gate, "GloomberbClient", _FakeClient)
    _FakeClient.builds = []
    _FakeClient.probes = []
    _FakeClient.verdict = SessionCheck(True, "ok", "accepted")
    _FakeClient.raises = None
    session_gate.reset_session_gate_cache()
    yield
    session_gate.reset_session_gate_cache()
    monkeypatch.setattr(session_gate, "_clock", None)


def _authenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    monkeypatch.setenv(GLOOMBERB_SESSION_COOKIE_ENV, _FAKE_COOKIE)


# -- acceptance: no secret means hidden, and it costs zero HTTP -----------------


def test_no_cookie_hides_the_tools_and_makes_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """#5245's default-off path is unchanged: nothing configured, nothing called."""
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")

    status = session_gate.session_gate_status()

    assert status.authenticated is False
    assert status.code == "no_secret"
    assert status.probed is False, "nothing to validate means nothing was probed"
    assert _FakeClient.builds == [], "the gate must not build a client without a cookie"
    assert session_gate.gated_tools_advertised() is False


def test_blank_cookie_counts_as_no_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """A whitespace-only env var is absence, not a secret to validate."""
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    monkeypatch.setenv(GLOOMBERB_SESSION_COOKIE_ENV, "   ")

    status = session_gate.session_gate_status()

    assert status.code == "no_secret"
    assert _FakeClient.builds == []


def test_kill_switch_off_is_reported_before_the_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cookie alone does not enable anything: GLOOMBERB_ENABLED still overrides."""
    monkeypatch.setenv(GLOOMBERB_SESSION_COOKIE_ENV, _FAKE_COOKIE)

    status = session_gate.session_gate_status()

    assert status.authenticated is False
    assert status.code == "disabled"
    assert _FakeClient.builds == [], "the kill switch short-circuits before any request"


# -- acceptance: an invalid or expired secret is hidden, plus a warning ---------


def test_invalid_cookie_hides_the_tools_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _authenticated(monkeypatch)
    _FakeClient.verdict = SessionCheck(False, "auth_required", "HTTP 401")

    with caplog.at_level(logging.WARNING, logger=session_gate.__name__):
        status = session_gate.session_gate_status()

    assert status.authenticated is False
    assert status.code == "auth_required"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "an invalid secret must warn, not fail silently"
    assert session_gate._LOGIN_HINT in warnings[0].getMessage()
    assert session_gate.gated_tools_advertised() is False


def test_expired_cookie_is_reported_as_auth_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticated(monkeypatch)
    _FakeClient.verdict = SessionCheck(False, "auth_required", "HTTP 401")

    assert session_gate.session_gate_status().code == "auth_required"


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        (SessionCheck(False, "probe_failed", "TimeoutError"), "probe_failed"),
        (SessionCheck(False, "upstream_error", "HTTP 503"), "upstream_error"),
    ],
)
def test_transport_and_upstream_faults_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    verdict: SessionCheck,
    expected: str,
) -> None:
    """A 5xx or a timeout is not evidence of a good session — it is no evidence."""
    _authenticated(monkeypatch)
    _FakeClient.verdict = verdict

    status = session_gate.session_gate_status()

    assert status.authenticated is False
    assert status.code == expected


def test_an_exception_inside_the_probe_fails_closed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _authenticated(monkeypatch)
    _FakeClient.raises = RuntimeError("transport exploded")

    with caplog.at_level(logging.WARNING, logger=session_gate.__name__):
        status = session_gate.session_gate_status()

    assert status.authenticated is False
    assert status.code == "probe_failed"
    assert status.detail == "RuntimeError", "the class name is safe to log, the message is not"
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# -- acceptance: a valid secret advertises the tools ----------------------------


def test_valid_cookie_advertises_the_gated_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticated(monkeypatch)

    status = session_gate.session_gate_status()

    assert status.authenticated is True
    assert status.code == "ok"
    assert status.probed is True
    assert session_gate.gated_tools_advertised() is True


def test_login_validates_a_candidate_cookie_that_is_not_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`gloomberb login` checks a pasted cookie before it is written anywhere."""
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    _FakeClient.verdict = SessionCheck(True, "ok", "accepted")

    status = session_gate.session_gate_status(cookie="  a-pasted-cookie  ")

    assert status.authenticated is True
    assert _FakeClient.builds == [{"session_cookie": "a-pasted-cookie"}]
    assert "a-pasted-cookie" not in session_gate.session_gate_status().detail


def test_login_rejects_a_bad_candidate_and_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GLOOMBERB_ENABLED_ENV, "1")
    _FakeClient.verdict = SessionCheck(False, "auth_required", "HTTP 401")

    status = session_gate.session_gate_status(cookie="a-wrong-cookie")

    assert status.authenticated is False
    assert status.code == "auth_required"


# -- the two properties the design rests on ------------------------------------


def test_one_probe_per_ttl_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeat list calls inside the TTL window reuse the verdict and stay silent."""
    _authenticated(monkeypatch)
    clock = [1000.0]
    monkeypatch.setattr(session_gate, "_clock", lambda: clock[0])

    first = session_gate.session_gate_status()
    second = session_gate.session_gate_status()
    third = session_gate.session_gate_status()

    assert (first.authenticated, second.authenticated, third.authenticated) == (True, True, True)
    assert len(_FakeClient.probes) == 1, "the TTL window must cost exactly one request"

    # One second past the window the verdict is re-proved.
    clock[0] += DEFAULT_CACHE_TTL_SECONDS + 1
    assert session_gate.session_gate_status().authenticated is True
    assert len(_FakeClient.probes) == 2


def test_a_new_cookie_never_inherits_the_previous_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cache key is the cookie fingerprint, so replacing the secret re-probes."""
    _authenticated(monkeypatch)
    assert session_gate.session_gate_status().authenticated is True

    monkeypatch.setenv(GLOOMBERB_SESSION_COOKIE_ENV, "a-different-cookie")
    _FakeClient.verdict = SessionCheck(False, "auth_required", "HTTP 401")

    assert session_gate.session_gate_status().authenticated is False
    assert len(_FakeClient.probes) == 2


def test_reset_drops_the_cached_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticated(monkeypatch)
    assert session_gate.session_gate_status().authenticated is True

    session_gate.reset_session_gate_cache()
    assert session_gate.session_gate_status().authenticated is True
    assert len(_FakeClient.probes) == 2


# -- the cookie never leaks into the cache, the warning or the status ----------


def test_the_cache_never_holds_the_cookie_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticated(monkeypatch)
    session_gate.session_gate_status()

    assert session_gate._cache, "the verdict must be cached"
    for key, (stamp, status) in session_gate._cache.items():
        assert _FAKE_COOKIE not in key
        assert _FAKE_COOKIE not in status.detail
        assert key == session_cache_fingerprint(_FAKE_COOKIE), "keys are fingerprints"
        assert isinstance(stamp, float)


def test_the_warning_text_never_carries_the_cookie(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _authenticated(monkeypatch)
    _FakeClient.verdict = SessionCheck(False, "auth_required", "HTTP 401")

    with caplog.at_level(logging.DEBUG):
        session_gate.session_gate_status()

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert _FAKE_COOKIE not in blob
    assert session_gate._LOGIN_HINT in blob, "the operator is told how to fix it"


def test_the_login_hint_names_the_env_var_the_command_and_the_wrangler_put() -> None:
    hint = session_gate._LOGIN_HINT

    assert GLOOMBERB_SESSION_COOKIE_ENV in hint
    assert "digiquant gloomberb login" in hint
    assert "wrangler secret put GLOOMBERB_SESSION_COOKIE" in hint


# --- the acceptance case itself: the MCP tool list (#2752) ---------------------
#
# The brief's first acceptance test is "with no secret the tools are absent from
# the MCP/API tool list". These go through `create_mcp_server` for real, with the
# real gate running against the counted fake client, so a registration change
# that re-advertises a session tool without a valid cookie fails here.


def _advertised_tool_names() -> set[str]:
    # The `mcp` extra is optional and the `digiquant` CI lane does not install
    # it, so `create_mcp_server` raises ImportError there. Every other MCP test
    # file guards with a MODULE-level importorskip, which would silently skip
    # this file's 17 gate tests as well in exactly that lane. The guard belongs
    # on the helper: a function-level importorskip skips only the calling test,
    # so the pure gate tests keep running and the four surface tests skip.
    pytest.importorskip("mcp.server.fastmcp")
    from digiquant.mcp_server import create_mcp_server

    return {tool.name for tool in create_mcp_server()._tool_manager.list_tools()}


def _session_gated_names() -> set[str]:
    from digiquant.data.gloomberb.entitlements import TOOL_ENTITLEMENTS

    return {
        name
        for name, entitlement in TOOL_ENTITLEMENTS.items()
        if entitlement in {"session", "preview", "pro"}
    }


def test_without_a_secret_no_session_tool_is_advertised(monkeypatch: pytest.MonkeyPatch) -> None:
    advertised = _advertised_tool_names()
    gated = _session_gated_names()

    assert gated, "the gate would be vacuous with no session-gated tools to hide"
    assert not (advertised & gated), (
        f"{len(advertised & gated)} session tools advertised with no cookie: "
        f"{sorted(advertised & gated)[:5]}"
    )


def test_an_expired_cookie_hides_the_family_too(monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticated(monkeypatch)
    _FakeClient.verdict = SessionCheck(False, "auth_required", "HTTP 401")

    assert not (_advertised_tool_names() & _session_gated_names())


def test_a_valid_cookie_advertises_the_whole_session_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _authenticated(monkeypatch)
    _FakeClient.verdict = SessionCheck(True, "ok", "accepted by api.gloom.sh")

    missing = _session_gated_names() - _advertised_tool_names()

    assert not missing, f"{len(missing)} session tools still hidden with a valid cookie"


def test_the_free_family_is_never_touched_by_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: the gate must hide the 41 gated tools and nothing else."""
    from digiquant.data.gloomberb.entitlements import TOOL_ENTITLEMENTS

    _FakeClient.verdict = SessionCheck(True, "ok", "accepted by api.gloom.sh")
    _authenticated(monkeypatch)
    with_cookie = _advertised_tool_names()

    monkeypatch.delenv(GLOOMBERB_SESSION_COOKIE_ENV)
    _FakeClient.verdict = None
    without_cookie = _advertised_tool_names()

    free = {n for n, e in TOOL_ENTITLEMENTS.items() if e == "free"}
    assert free & without_cookie == free & with_cookie, (
        "the free family must be advertised identically with and without a cookie"
    )
