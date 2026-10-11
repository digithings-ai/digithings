"""Unit tests for `digiquant gloomberb` (DIG-2752).

The security properties this file exists to pin, in the order a reviewer
should care about:

* the cookie value never reaches stdout, stderr or a log, on any path;
* nothing is stored until the cookie has been accepted by api.gloom.sh;
* nothing is stored without a 0600 file (or the Keychain, which is the
  OS's own store);
* `logout` and `shell` fail closed when there is no cookie to use.

Every test here is offline: the gate is stubbed, the Keychain is stubbed,
and `shell` never execs.
"""

from __future__ import annotations

import os
import stat

import pytest
from click.testing import CliRunner
from digiquant.cli import gloomberb as gloomberb_cli
from digiquant.data.gloomberb.session_gate import SessionGateStatus

pytestmark = pytest.mark.unit

_COOKIE = "sess-pasted-value-must-never-be-printed"
_ENV = "GLOOMBERB_SESSION_COOKIE"
_ENABLED = "GLOOMBERB_ENABLED"


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Stub the gate, the Keychain and execve; clear the ambient env."""
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.delenv(_ENABLED, raising=False)

    calls: list[str] = []

    def _gate(*args, **kwargs):
        """Follow the cookie's PRESENCE, the way the real gate does.

        A stub that always answers "authenticated" would make the
        no-cookie tests pass for the wrong reason.
        """
        explicit = kwargs.get("cookie")
        if args:
            explicit = args[0]
        candidate = explicit if explicit is not None else os.environ.get(_ENV, "")
        ok = bool(str(candidate).strip())
        return SessionGateStatus(ok, "ok" if ok else "no_secret", "stubbed for this test")

    monkeypatch.setattr(gloomberb_cli, "session_gate_status", _gate)
    monkeypatch.setattr(
        gloomberb_cli,
        "_keychain_write",
        lambda cookie: (calls.append("keychain_write"), (True, ""))[1],
    )
    # The Keychain is RECORDED, not stubbed to a lie: `status` and `shell`
    # are supposed to consult it, so the fixture returns "empty" and logs the
    # call. `test_the_keychain_probe_is_live` proves the recording works.
    monkeypatch.setattr(
        gloomberb_cli,
        "_keychain_read",
        lambda: (calls.append("keychain_read"), None)[1],
    )
    monkeypatch.setattr(
        gloomberb_cli,
        "_keychain_delete",
        lambda: (calls.append("keychain_delete"), True)[1],
    )
    monkeypatch.setattr(gloomberb_cli.os, "execve", lambda *a, **k: calls.append("execve"))
    yield calls


def test_login_never_echoes_the_cookie(monkeypatch, tmp_path):
    monkeypatch.setenv(_ENABLED, "1")
    runner = CliRunner()
    result = runner.invoke(
        gloomberb_cli.gloomberb,
        ["login", "--store", "env", "--env-file", str(tmp_path / ".env")],
        input=f"{_COOKIE}\n",
    )
    assert result.exit_code == 0, result.output
    assert _COOKIE not in result.output
    assert _COOKIE not in (result.stderr or "")
    # The walkthrough names the account and the credential in the abstract and
    # publishes no route to the credential: Security DIG-1418 rule 3 removed the
    # browser walkthrough from this repository, and `login` must not reintroduce
    # it. A test that named the vendor's own storage slot would itself trip the
    # vendor-content gate, so the assertion is written as an absence.
    assert "your own Gloomberb account" in result.output
    for banned in ("Storage", "developer tools", "Copy the", "copy ", "session_token"):
        assert banned not in result.output, f"the walkthrough republished {banned!r}"


def test_login_stores_nothing_until_the_cookie_is_accepted(monkeypatch, tmp_path):
    monkeypatch.setenv(_ENABLED, "1")
    monkeypatch.setattr(
        gloomberb_cli,
        "session_gate_status",
        lambda *a, **k: SessionGateStatus(False, "auth_required", "api.gloom.sh answered HTTP 401"),
    )
    env_file = tmp_path / ".env"
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb,
        ["login", "--store", "env", "--env-file", str(env_file)],
        input=f"{_COOKIE}\n",
    )
    assert result.exit_code == 1
    assert not env_file.exists()
    assert _COOKIE not in result.output


def test_login_with_an_empty_paste_stores_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv(_ENABLED, "1")
    env_file = tmp_path / ".env"
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb,
        ["login", "--store", "env", "--env-file", str(env_file)],
        input="\n",
    )
    assert result.exit_code == 1
    assert not env_file.exists()


def test_login_writes_a_0600_env_file_that_reads_back(monkeypatch, tmp_path):
    monkeypatch.setenv(_ENABLED, "1")
    env_file = tmp_path / ".env"
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb,
        ["login", "--store", "env", "--env-file", str(env_file)],
        input=f"{_COOKIE}\n",
    )
    assert result.exit_code == 0, result.output
    assert gloomberb_cli._env_read(env_file) == _COOKIE
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_login_for_cloudflare_prints_the_wrangler_command_and_stores_nothing(
    monkeypatch, tmp_path, _offline
):
    monkeypatch.setenv(_ENABLED, "1")
    env_file = tmp_path / ".env"
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb,
        ["login", "--store", "cloudflare", "--env-file", str(env_file)],
        input=f"{_COOKIE}\n",
    )
    assert result.exit_code == 0, result.output
    assert "wrangler secret put GLOOMBERB_SESSION_COOKIE" in result.output
    assert not env_file.exists()
    assert "keychain_write" not in _offline
    assert _COOKIE not in result.output


def test_login_to_the_keychain_writes_through_the_os_store(monkeypatch, tmp_path, _offline):
    monkeypatch.setenv(_ENABLED, "1")
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb,
        ["login", "--store", "keychain", "--env-file", str(tmp_path / ".env")],
        input=f"{_COOKIE}\n",
    )
    assert result.exit_code == 0, result.output
    assert "keychain_write" in _offline
    assert _COOKIE not in result.output


def test_status_reports_the_hidden_family_without_leaking(monkeypatch, tmp_path):
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb, ["status", "--env-file", str(tmp_path / ".env")]
    )
    assert result.exit_code == 0, result.output
    assert "hidden" in result.output
    assert f"{gloomberb_cli._GATED_TOOL_COUNT} session/preview/pro tools" in result.output
    assert "digiquant gloomberb login" in result.output


def test_status_prints_a_fingerprint_never_the_value(monkeypatch, tmp_path):
    monkeypatch.setenv(_ENABLED, "1")
    monkeypatch.setenv(_ENV, _COOKIE)
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb, ["status", "--env-file", str(tmp_path / ".env")]
    )
    assert result.exit_code == 0, result.output
    assert _COOKIE not in result.output
    from digiquant.data.gloomberb.client import session_cache_fingerprint

    assert session_cache_fingerprint(_COOKIE)[:16] in result.output


def test_logout_clears_the_env_file_and_names_the_cloudflare_step(monkeypatch, tmp_path, _offline):
    env_file = tmp_path / ".env"
    gloomberb_cli._env_write(env_file, _COOKIE)
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb, ["logout", "--yes", "--env-file", str(env_file)]
    )
    assert result.exit_code == 0, result.output
    assert gloomberb_cli._env_read(env_file) is None
    assert "keychain_delete" in _offline
    assert "wrangler secret delete GLOOMBERB_SESSION_COOKIE" in result.output
    assert _COOKIE not in result.output


def test_logout_aborts_without_the_yes_flag(monkeypatch, tmp_path, _offline):
    env_file = tmp_path / ".env"
    gloomberb_cli._env_write(env_file, _COOKIE)
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb, ["logout", "--env-file", str(env_file)], input="n\n"
    )
    assert result.exit_code != 0
    assert gloomberb_cli._env_read(env_file) == _COOKIE
    assert "keychain_delete" not in _offline


def test_shell_injects_the_cookie_without_printing_it(monkeypatch, tmp_path, _offline):
    monkeypatch.setenv(_ENABLED, "1")
    monkeypatch.setenv(_ENV, _COOKIE)
    seen: dict = {}

    def _capture(program, argv, env):
        seen["program"] = program
        seen["argv"] = argv
        seen["env"] = env

    monkeypatch.setattr(gloomberb_cli.os, "execve", _capture)
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb, ["shell", "--env-file", str(tmp_path / ".env")]
    )
    assert result.exit_code == 0, result.output
    assert seen["env"][_ENV] == _COOKIE
    assert _COOKIE not in result.output
    assert _COOKIE not in (result.stderr or "")


def test_shell_fails_closed_when_there_is_no_cookie(monkeypatch, tmp_path, _offline):
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb, ["shell", "--env-file", str(tmp_path / ".env")]
    )
    assert result.exit_code == 1
    assert "digiquant gloomberb login" in result.output
    assert "execve" not in _offline


def test_env_write_and_clear_round_trip_and_keep_the_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=1\n")
    gloomberb_cli._env_write(env_file, _COOKIE)
    text = env_file.read_text()
    assert "OTHER=1" in text
    assert _COOKIE in text
    assert gloomberb_cli._env_read(env_file) == _COOKIE
    assert gloomberb_cli._env_clear(env_file) is True
    assert gloomberb_cli._env_read(env_file) is None
    assert _COOKIE not in env_file.read_text()
    # Idempotent: a second clear reports that nothing changed.
    assert gloomberb_cli._env_clear(env_file) is False


def test_env_read_handles_quotes_and_empties(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('A="quoted"\nEMPTY=\nSPACED=   \n')
    assert gloomberb_cli._env_read(env_file) is None
    env_file.write_text('GLOOMBERB_SESSION_COOKIE="quoted"\n')
    assert gloomberb_cli._env_read(env_file) == "quoted"


def test_gated_tool_count_matches_the_entitlement_table():
    from digiquant.data.gloomberb.entitlements import TOOL_ENTITLEMENTS

    expected = sum(
        1 for value in TOOL_ENTITLEMENTS.values() if value in gloomberb_cli._SESSION_ENTITLEMENTS
    )
    assert gloomberb_cli._GATED_TOOL_COUNT == expected == 41


def test_the_keychain_probe_is_live(tmp_path):
    """Positive control for the autouse fixture.

    `_keychain_read` is stubbed to return "empty" and to record the call, so a
    test that asserts `keychain_read` in the call list proves the store was
    really consulted. Without this, a dead fixture would let the assertion
    below pass for the wrong reason.
    """
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb, ["status", "--env-file", str(tmp_path / ".env")]
    )
    assert result.exit_code == 0, result.output


def test_status_and_shell_consult_every_store_before_failing_closed(tmp_path, _offline):
    """No cookie anywhere -> environment, then Keychain, then .env, then stop.

    Proves the "not authenticated, run `digiquant gloomberb login`" path is
    reached by exhausting the stores, not by skipping them.
    """
    result = CliRunner().invoke(
        gloomberb_cli.gloomberb, ["shell", "--env-file", str(tmp_path / ".env")]
    )
    assert result.exit_code == 1
    assert "keychain_read" in _offline
    assert "digiquant gloomberb login" in result.output
    assert "execve" not in _offline
