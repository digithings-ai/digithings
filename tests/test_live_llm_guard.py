"""The paid-LLM guard: no test run may reach a paid API unless it opts in."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.paid_llm_guard import (
    ALLOW_LIVE_ENV,
    fail_fast_message,
    install,
    is_paid_llm_host,
    live_llm_allowed,
)

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_CHILD_ENV_KEYS = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TMP",
    "TEMP",
    "USER",
    "LOGNAME",
    "VIRTUAL_ENV",
)
_DUMMY_KEY = "not-a-credential"


def _packages_with_own_pytest_config(repo: Path) -> list[Path]:
    found: list[Path] = []
    for pyproject in sorted(repo.glob("*/pyproject.toml")):
        text = pyproject.read_text(encoding="utf-8")
        if "[tool.pytest.ini_options]" in text:
            found.append(pyproject.parent)
    return found


_PACKAGE_ROOTS = _packages_with_own_pytest_config(_REPO)


@pytest.mark.parametrize(
    "host",
    [
        "api.cheaperinference.com",
        "API.CheaperInference.com.",
        b"openrouter.ai",
        "api.openai.com",
        "generativelanguage.googleapis.com",
        "api.deepseek.com",
    ],
)
def test_paid_hosts_are_recognised(host: object) -> None:
    assert is_paid_llm_host(host)


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "localhost", "example.com", "notcheaperinference.com", None, 443]
)
def test_other_hosts_are_not(host: object) -> None:
    assert not is_paid_llm_host(host)


def test_resolving_a_paid_host_is_blocked_this_session() -> None:
    if live_llm_allowed():
        pytest.skip(f"{ALLOW_LIVE_ENV} is set")
    with pytest.raises(OSError, match="live LLM call blocked"):
        socket.getaddrinfo("api.cheaperinference.com", 443)


def test_loopback_still_resolves() -> None:
    assert socket.getaddrinfo("127.0.0.1", 80)


def test_cheaperinference_key_is_absent_this_session() -> None:
    if live_llm_allowed():
        pytest.skip(f"{ALLOW_LIVE_ENV} is set")
    assert not (os.environ.get("CHEAPERINFERENCE_API_KEY") or "").strip()


def test_opt_in_values() -> None:
    assert live_llm_allowed({ALLOW_LIVE_ENV: "1"})
    assert live_llm_allowed({ALLOW_LIVE_ENV: "true"})
    assert not live_llm_allowed({ALLOW_LIVE_ENV: "0"})
    assert not live_llm_allowed({})


def test_fail_fast_message_names_the_variable_not_the_value() -> None:
    message = fail_fast_message({"CHEAPERINFERENCE_API_KEY": _DUMMY_KEY})
    assert message is not None
    assert "CHEAPERINFERENCE_API_KEY is set" in message
    assert _DUMMY_KEY not in message
    assert fail_fast_message({}) is None


def test_install_reports_the_house_key_without_leaking_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHEAPERINFERENCE_API_KEY", _DUMMY_KEY)
    monkeypatch.delenv(ALLOW_LIVE_ENV, raising=False)
    message = install()
    assert message is not None
    assert "CHEAPERINFERENCE_API_KEY is set" in message
    assert _DUMMY_KEY not in message


def test_install_scrubs_other_paid_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHEAPERINFERENCE_API_KEY", raising=False)
    monkeypatch.delenv(ALLOW_LIVE_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", _DUMMY_KEY)
    install()
    assert "OPENAI_API_KEY" not in os.environ


def test_every_package_pytest_rootdir_has_the_guard() -> None:
    missing = [
        package.name
        for package in _PACKAGE_ROOTS
        if "paid_llm_guard" not in (package / "conftest.py").read_text(encoding="utf-8")
    ]
    assert missing == []
    bodies = [(package / "conftest.py").read_text(encoding="utf-8") for package in _PACKAGE_ROOTS]
    assert len(set(bodies)) == 1
    # tests/conftest.py is the conftest an outside testpath actually loads.
    assert "paid_llm_guard" in (_REPO / "tests" / "conftest.py").read_text(encoding="utf-8")


def _child_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _CHILD_ENV_KEYS if key in os.environ}
    env["CHEAPERINFERENCE_API_KEY"] = _DUMMY_KEY
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _invocations() -> list[tuple[str, Path, list[str]]]:
    """How a person actually starts pytest, not a forced --rootdir.

    A forced rootdir skips the conftest pytest really loads. The repo case
    points at one file so a broken guard fails before it collects the tree.
    Package cases use that package's own testpaths (``cd <package> && pytest``).
    """
    rows: list[tuple[str, Path, list[str]]] = [
        ("repo", _REPO, ["tests/test_live_llm_guard.py"]),
        ("digillm-from-repo", _REPO, ["digillm/tests/test_fail_fast.py"]),
        ("digisearch-from-repo", _REPO, ["digisearch/tests/test_web_search_models.py"]),
    ]
    rows.extend((package.name, package, []) for package in _PACKAGE_ROOTS)
    return rows


@pytest.mark.parametrize(
    ("label", "cwd", "extra"),
    _invocations(),
    ids=[row[0] for row in _invocations()],
)
def test_house_key_stops_that_invocation(label: str, cwd: Path, extra: list[str]) -> None:
    """pytest_configure exits 4 before collection, including package rootdirs."""
    del label
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "--override-ini",
            "addopts=",
            *extra,
        ],
        cwd=cwd,
        env=_child_env(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 4, output[-800:]
    assert "CHEAPERINFERENCE_API_KEY is set" in output
    assert _DUMMY_KEY not in output
