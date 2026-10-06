"""Tests for ``scripts/az-guard/az`` (DIG-1725).

The guard is the enforcement point for the DataTap Azure access register: it sits on PATH
ahead of the real ``az`` and refuses every command aimed at a subscription the register
does not authorise. These tests are the evidence that it fails closed, because "fails
closed" is a claim about what happens when something goes wrong, and the interesting
something is always the part nobody wrote down.

Two rules shape the suite:

- **No real ``az`` is ever executed.** A fake ``az`` records the argv it was handed and
  exits 0. ``AZ_GUARD_REAL_AZ`` pins the guard to it, so the suite does not depend on
  whether the machine running it has an Azure CLI installed.
- **No host state is read or written.** ``HOME``, ``AZURE_CONFIG_DIR``, the register and
  the refusal log are all pointed at ``tmp_path``. A test that read the developer's real
  ``~/.azure`` would be a test whose answer depends on whose laptop it ran on.

The suite lives under ``tests/scripts/`` and every test is marked ``unit``, which is what
the ``ruff-and-scripts`` CI lane runs.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIM = REPO_ROOT / "scripts" / "az-guard" / "az"
INSTALLER = REPO_ROOT / "scripts" / "az-guard" / "install.sh"
COMMITTED_REGISTER = REPO_ROOT / "config" / "datatap_azure_access_register.json"

#: The guard's documented refusal code: sysexits EX_CONFIG, not an Azure error code.
EXIT_REFUSED = 78

#: A row that is on nobody's register. Used as the "authorised" subscription where the
#: happy path needs one, so a future change to the committed register cannot silently
#: flip a refusal test into a pass.
AUTHORISED = "11111111-2222-3333-4444-555555555555"

#: An id that is syntactically fine and authorised for nobody.
UNLISTED = "99999999-8888-7777-6666-555555555555"

#: The four Azure contexts observed on the machine this was built for (DIG-1674). None is
#: classified, so none is authorised, and all four must be refused.
OBSERVED_PRODUCTION = "fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0"
OBSERVED_CONTEXTS: dict[str, str] = {
    "Datatap Trials": "0071922f-05ec-48aa-b20e-2a12333b0adf",
    "Subscription - dev": "8042941f-87db-4546-b3a4-0b720c1da146",
    "DataTap WebSite (PRODUCTION)": OBSERVED_PRODUCTION,
    "Test Subcription for Greenfield Deployment": "d4a34253-aa31-446e-b819-888af08ccf68",
}

_FAKE_AZ = '''#!/usr/bin/env python3
"""Fake `az`: record the argv it was handed, then succeed.

The point of the fake is that a refusal test can assert the real command was *not* reached,
which is the half of the behaviour a refusal message alone cannot show.
"""
import json
import os
import sys

with open(os.environ["FAKE_AZ_CALLS"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
sys.exit(0)
'''

#: Env vars the guard reads, asserted as an exact set so a future "temporary" escape hatch
#: (AZ_GUARD_BYPASS, AZURE_ALLOW_ANY) shows up as a failing test rather than as a hole.
#: None of them can widen the register: they choose paths and the exec target, never
#: permission. HOME is here because ``Path.home()`` reads it.
GUARD_ENV_VARS = {
    "AZ_GUARD_ACTIVE",
    "AZ_GUARD_LOG",
    "AZ_GUARD_REAL_AZ",
    "AZ_GUARD_REGISTER",
    "AZURE_CONFIG_DIR",
    "HOME",
    "LOGNAME",
    "PATH",
    "TMPDIR",
    "USER",
}


def _make_executable(path: Path) -> Path:
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


class Refusal:
    """One refusal: its exit code, what was printed, and what it named."""

    def __init__(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.exit_code = completed.returncode
        self.stdout = completed.stdout
        self.stderr = completed.stderr

    @property
    def reason(self) -> str:
        match = re.search(r"az guard: REFUSED \(([^)]+)\)", self.stderr)
        assert match is not None, f"no refusal line on stderr:\n{self.stderr}"
        return match.group(1)


class Guard:
    """Runs ``scripts/az-guard/az`` against a throwaway register, profile and log."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch
        self.fake_az_calls = tmp_path / "fake-az-calls.jsonl"

        fake_az = tmp_path / "fakebin" / "az"
        fake_az.parent.mkdir(parents=True, exist_ok=True)
        fake_az.write_text(_FAKE_AZ, encoding="utf-8")
        _make_executable(fake_az)

        self.register = tmp_path / "register.json"
        self.log = tmp_path / "az-guard-refusals.log"
        self.azure_dir = tmp_path / "azure"
        self.home = tmp_path / "home"
        self.azure_dir.mkdir(parents=True, exist_ok=True)
        self.home.mkdir(parents=True, exist_ok=True)

        # A profile with no [defaults] subscription: the state this machine is in after
        # the production account was signed out (DIG-1674, Decision 1).
        (self.azure_dir / "config").write_text("[cloud]\nname = AzureCloud\n", encoding="utf-8")

        monkeypatch.setenv("HOME", str(self.home))
        monkeypatch.setenv("AZURE_CONFIG_DIR", str(self.azure_dir))
        monkeypatch.setenv("AZ_GUARD_REGISTER", str(self.register))
        monkeypatch.setenv("AZ_GUARD_LOG", str(self.log))
        monkeypatch.setenv("FAKE_AZ_CALLS", str(self.fake_az_calls))
        monkeypatch.setenv("AZ_GUARD_REAL_AZ", str(fake_az))
        # The shim's shebang is `env python3`, so python3 must stay reachable on PATH.
        monkeypatch.setenv("PATH", os.pathsep.join([str(fake_az.parent), os.environ["PATH"]]))

    def write_register(self, subscriptions: object) -> Path:
        """Write a register whose ``authorized_subscriptions`` is exactly `subscriptions`."""
        self.register.write_text(
            json.dumps({"authorized_subscriptions": subscriptions}), encoding="utf-8"
        )
        return self.register

    def set_profile_default(self, subscription: str | None) -> None:
        """Write (or clear) the ``[defaults] subscription`` the local Azure profile holds."""
        if subscription is None:
            (self.azure_dir / "config").write_text("[cloud]\nname = AzureCloud\n", encoding="utf-8")
            return
        (self.azure_dir / "config").write_text(
            f"[cloud]\nname = AzureCloud\n\n[defaults]\nsubscription = {subscription}\n",
            encoding="utf-8",
        )

    def run(self, *argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(SHIM), *argv], capture_output=True, text=True, check=False)

    def refuse(self, *argv: str) -> Refusal:
        completed = self.run(*argv)
        assert completed.returncode == EXIT_REFUSED, (
            f"expected the guard to refuse (exit {EXIT_REFUSED}), got {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
        return Refusal(completed)

    @property
    def calls(self) -> list[list[str]]:
        """Every argv the fake ``az`` was handed. Empty means nothing was executed."""
        if not self.fake_az_calls.exists():
            return []
        return [
            json.loads(line)
            for line in self.fake_az_calls.read_text(encoding="utf-8").splitlines()
            if line
        ]

    @property
    def log_entries(self) -> list[dict[str, object]]:
        if not self.log.exists():
            return []
        return [
            json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line
        ]

    def last_log_entry(self) -> dict[str, object]:
        entries = self.log_entries
        assert entries, f"no refusal logged to {self.log}"
        return entries[-1]


@pytest.fixture
def guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Guard:
    return Guard(tmp_path, monkeypatch)


# ── the shim itself ──────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_shim_is_executable_and_asks_for_python3() -> None:
    mode = SHIM.stat().st_mode
    assert mode & stat.S_IXUSR, f"{SHIM} is not executable — run: chmod +x {SHIM}"
    assert SHIM.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")


@pytest.mark.unit
def test_shim_reads_only_the_env_vars_this_suite_allowlists() -> None:
    """Pins the no-bypass decision at the source level.

    A bypass env var would be a hole with a friendly name. Asserting the exact set of
    variables the guard reads makes adding one a deliberate act that breaks this test,
    instead of a line that looks harmless in review.
    """
    source = SHIM.read_text(encoding="utf-8")
    read: set[str] = set()
    for pattern in (
        r"os\.environ\.get\(\s*\"([A-Z_]+)\"",
        r"os\.environ\[\s*\"([A-Z_]+)\"",
        r"os\.getenv\(\s*\"([A-Z_]+)\"",
    ):
        read |= set(re.findall(pattern, source))
    unexpected = read - GUARD_ENV_VARS
    assert not unexpected, f"the guard reads undeclared env vars: {sorted(unexpected)}"
    for name in sorted(read):
        assert not re.search(r"BYPASS|ALLOW|SKIP|DISABLE|OVERRIDE", name), (
            f"{name} reads like a bypass switch"
        )


# ── the register ─────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_committed_register_authorises_nothing() -> None:
    """The enforced state: the register on disk lists zero authorised subscriptions."""
    data = json.loads(COMMITTED_REGISTER.read_text(encoding="utf-8"))
    assert data["authorized_subscriptions"] == []
    assert data["last_changed"]
    assert data["changed_by"]


@pytest.mark.unit
def test_authorised_subscription_reaches_the_real_az(guard: Guard) -> None:
    guard.write_register([AUTHORISED])
    completed = guard.run("account", "show", "--subscription", AUTHORISED)

    assert completed.returncode == 0, completed.stderr
    assert guard.calls == [["account", "show", "--subscription", AUTHORISED]]
    assert not guard.log_entries, "an authorised command must not write a refusal"


@pytest.mark.unit
def test_unlisted_subscription_is_refused_and_nothing_is_executed(guard: Guard) -> None:
    guard.write_register([AUTHORISED])
    refusal = guard.refuse("account", "show", "--subscription", UNLISTED)

    assert refusal.reason == "subscription-not-authorised"
    assert guard.calls == [], "the guard executed the real az after refusing"


@pytest.mark.unit
@pytest.mark.parametrize("context", sorted(OBSERVED_CONTEXTS))
def test_all_four_observed_contexts_are_refused_against_the_committed_register(
    guard: Guard, context: str
) -> None:
    """The DoD claim, as a test: against the register this repo ships, none of the four
    Azure contexts seen on the machine is reachable."""
    subscription = OBSERVED_CONTEXTS[context]
    guard.monkeypatch.delenv("AZ_GUARD_REGISTER", raising=False)

    refusal = guard.refuse("account", "show", "--subscription", subscription)

    assert refusal.reason == "register-empty"
    assert guard.calls == []
    assert guard.last_log_entry()["subscription"] == subscription


@pytest.mark.unit
def test_empty_register_refuses_everything_including_reads(guard: Guard) -> None:
    guard.write_register([])
    refusal = guard.refuse("vm", "list", "--subscription", AUTHORISED)

    assert refusal.reason == "register-empty"
    assert guard.calls == []


@pytest.mark.unit
def test_missing_register_refuses_and_never_falls_through(guard: Guard) -> None:
    guard.register.unlink(missing_ok=True)
    refusal = guard.refuse("account", "show", "--subscription", AUTHORISED)

    assert refusal.reason == "register-missing"
    assert guard.calls == []


@pytest.mark.unit
def test_unreadable_register_refuses(guard: Guard) -> None:
    guard.register.unlink(missing_ok=True)
    guard.register.mkdir()  # a path that exists and cannot be read as a file
    refusal = guard.refuse("account", "show", "--subscription", AUTHORISED)

    assert refusal.reason == "register-unreadable"
    assert guard.calls == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("body", "label"),
    [
        ("this is not json", "unparseable"),
        ('["a", "b"]', "a list, not an object"),
        ('{"authorized_subscriptions": "everything"}', "a string, not a list"),
        (f'{{"subscriptions": ["{AUTHORISED}"]}}', "the wrong key"),
    ],
)
def test_malformed_register_refuses(guard: Guard, body: str, label: str) -> None:
    guard.register.write_text(body, encoding="utf-8")
    refusal = guard.refuse("account", "show", "--subscription", AUTHORISED)

    assert refusal.reason == "register-malformed", label
    assert guard.calls == []


@pytest.mark.unit
def test_extra_keys_cannot_open_access(guard: Guard) -> None:
    """A plausible-looking escape hatch written into the register is still nothing."""
    guard.register.write_text(
        json.dumps(
            {
                "_readme": "written by an agent trying to be helpful",
                "authorized_subscriptions": [],
                "allow_all": True,
                "allow": [AUTHORISED],
                "denied": [],
            }
        ),
        encoding="utf-8",
    )
    refusal = guard.refuse("account", "show", "--subscription", AUTHORISED)

    assert refusal.reason == "register-empty"
    assert guard.calls == []


@pytest.mark.unit
def test_non_uuid_rows_do_not_authorise(guard: Guard) -> None:
    """Names and half-written ids are noise, and noise does not open a door."""
    guard.write_register(["DataTap WebSite", AUTHORISED[:-1], "not-a-uuid"])
    refusal = guard.refuse("account", "show", "--subscription", AUTHORISED)

    assert refusal.reason == "register-empty"
    assert guard.calls == []


# ── resolving the target subscription ────────────────────────────────────────────
@pytest.mark.unit
def test_indeterminate_subscription_refuses(guard: Guard) -> None:
    """No flag and no profile default: the guard cannot tell which subscription this is,
    and the default context is production, so it refuses."""
    guard.write_register([AUTHORISED])
    refusal = guard.refuse("account", "list")

    assert refusal.reason == "indeterminate-subscription"
    assert guard.calls == []


@pytest.mark.unit
def test_profile_default_is_the_target_and_production_is_refused(guard: Guard) -> None:
    """This is the SEV1 shape: no flag on the command line, production as the default."""
    guard.write_register([AUTHORISED])
    guard.set_profile_default(OBSERVED_PRODUCTION)
    refusal = guard.refuse("group", "list")

    assert refusal.reason == "subscription-not-authorised"
    entry = guard.last_log_entry()
    assert entry["subscription"] == OBSERVED_PRODUCTION
    assert entry["subscription_source"] == "profile-default"


@pytest.mark.unit
def test_profile_default_on_the_register_reaches_the_real_az(guard: Guard) -> None:
    guard.write_register([AUTHORISED])
    guard.set_profile_default(AUTHORISED)
    completed = guard.run("group", "list")

    assert completed.returncode == 0, completed.stderr
    assert guard.calls == [["group", "list"]]


@pytest.mark.unit
def test_command_line_beats_the_profile_default(guard: Guard) -> None:
    guard.write_register([AUTHORISED])
    guard.set_profile_default(OBSERVED_PRODUCTION)
    completed = guard.run("group", "list", "--subscription", AUTHORISED)

    assert completed.returncode == 0, completed.stderr
    assert guard.calls == [["group", "list", "--subscription", AUTHORISED]]


@pytest.mark.unit
def test_subscription_name_is_refused_not_resolved(guard: Guard) -> None:
    """``--subscription "DataTap WebSite"`` would mean asking Azure which subscription the
    operator meant. Deciding that a name is non-production is the act the register
    forbids, so the guard refuses the name."""
    guard.write_register([AUTHORISED])
    refusal = guard.refuse("group", "list", "--subscription", "DataTap WebSite")

    assert refusal.reason == "subscription-not-an-id"
    assert guard.calls == []


@pytest.mark.unit
def test_selector_flag_with_no_value_refuses(guard: Guard) -> None:
    guard.write_register([AUTHORISED])
    refusal = guard.refuse("group", "list", "--subscription")

    assert refusal.reason == "indeterminate-subscription"
    assert guard.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("flag", ["--subscription", "--sub", "--subs", "--subscriptions", "-s"])
def test_every_selector_spelling_is_checked(guard: Guard, flag: str) -> None:
    """Regression pin for the obvious bypass: ``az`` resolves a long option by unambiguous
    prefix, so a guard that only reads ``--subscription`` is a guard with a hole in it."""
    guard.write_register([AUTHORISED])
    refusal = guard.refuse("group", "list", flag, OBSERVED_PRODUCTION)

    assert refusal.reason == "subscription-not-authorised", flag
    assert guard.last_log_entry()["subscription"] == OBSERVED_PRODUCTION


@pytest.mark.unit
def test_two_different_targets_on_one_command_line_refuse(guard: Guard) -> None:
    guard.write_register([AUTHORISED])
    refusal = guard.refuse(
        "group",
        "list",
        "--subscription",
        AUTHORISED,
        "--subscription",
        OBSERVED_PRODUCTION,
    )

    assert refusal.reason == "ambiguous-subscription"
    assert guard.calls == []


@pytest.mark.unit
def test_the_same_target_twice_is_not_ambiguous(guard: Guard) -> None:
    guard.write_register([AUTHORISED])
    completed = guard.run(
        "group", "list", "--subscription", AUTHORISED, "--subscription", AUTHORISED
    )

    assert completed.returncode == 0, completed.stderr


# ── executing the authorised command ─────────────────────────────────────────────
@pytest.mark.unit
def test_recursive_invocation_refuses(guard: Guard, monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard marks its own child with AZ_GUARD_ACTIVE, so an ``az`` that re-enters the
    guard refuses instead of exec-looping forever."""
    guard.write_register([AUTHORISED])
    monkeypatch.setenv("AZ_GUARD_ACTIVE", "1")
    refusal = guard.refuse("account", "show", "--subscription", AUTHORISED)

    assert refusal.reason == "recursive-invocation"
    assert guard.calls == []


@pytest.mark.unit
def test_no_real_az_refuses_even_an_authorised_subscription(
    guard: Guard, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails closed on its own side too: an authorised command with nothing to exec is a
    refusal, not a silent success and not a crash."""
    guard.write_register([AUTHORISED])
    monkeypatch.setenv("AZ_GUARD_REAL_AZ", str(guard.tmp_path / "no-such-az"))
    refusal = guard.refuse("account", "show", "--subscription", AUTHORISED)

    assert refusal.reason == "real-az-not-found"


# ── the log ──────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_refusal_is_logged_with_timestamp_subscription_and_command(guard: Guard) -> None:
    guard.write_register([AUTHORISED])
    guard.refuse("vm", "list", "--subscription", OBSERVED_PRODUCTION)

    entry = guard.last_log_entry()
    assert entry["event"] == "az-guard refusal"
    assert entry["reason"] == "subscription-not-authorised"
    assert entry["subscription"] == OBSERVED_PRODUCTION
    assert entry["subscription_source"] == "command-line"
    assert entry["register"] == str(guard.register)
    assert entry["register_authorized_count"] == 1
    assert entry["command"] == ["vm", "list", "--subscription", OBSERVED_PRODUCTION]
    assert entry["cwd"] == os.getcwd()

    parsed = datetime.fromisoformat(str(entry["ts"]).replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, "the log timestamp must be timezone-aware"


@pytest.mark.unit
def test_every_refusal_appends_its_own_line(guard: Guard) -> None:
    guard.write_register([AUTHORISED])
    guard.refuse("vm", "list", "--subscription", UNLISTED)
    guard.refuse("vm", "list", "--subscription", UNLISTED.upper())

    reasons = [entry["reason"] for entry in guard.log_entries]
    assert reasons == ["subscription-not-authorised", "subscription-not-authorised"]


@pytest.mark.unit
def test_sensitive_option_values_are_redacted(guard: Guard) -> None:
    """The guard must not become a credential store by logging what it was asked to pass."""
    guard.write_register([AUTHORISED])
    refusal = guard.refuse(
        "vm",
        "create",
        "--subscription",
        UNLISTED,
        "--password",
        "hunter2",
        "--client-secret=secret-sauce",
    )

    assert "hunter2" not in refusal.stderr
    assert "secret-sauce" not in refusal.stderr
    entry = guard.last_log_entry()
    assert "hunter2" not in json.dumps(entry)
    assert "secret-sauce" not in json.dumps(entry)
    assert "<redacted>" in json.dumps(entry)


@pytest.mark.unit
def test_an_unwritable_log_still_refuses(guard: Guard) -> None:
    """A broken log must never downgrade a refusal. Losing the log is a problem to fix;
    losing the control would be a worse one."""
    guard.write_register([AUTHORISED])
    guard.log.unlink(missing_ok=True)
    guard.log.mkdir()
    refusal = guard.refuse("account", "show", "--subscription", UNLISTED)

    assert refusal.reason == "subscription-not-authorised"
    assert "WARNING" in refusal.stderr
    assert guard.calls == []


@pytest.mark.unit
def test_no_environment_variable_bypasses_the_guard(
    guard: Guard, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Names a future agent would reach for. None of them does anything."""
    guard.write_register([AUTHORISED])
    for name, value in {
        "AZ_GUARD_BYPASS": "1",
        "AZURE_SUBSCRIPTION_ID": AUTHORISED,
        "DIGITHINGS_ALLOW_PROTECTED": "1",
        "CI": "true",
        "DEBUG": "1",
    }.items():
        monkeypatch.setenv(name, value)

    refusal = guard.refuse("account", "show", "--subscription", OBSERVED_PRODUCTION)

    assert refusal.reason == "subscription-not-authorised"
    assert guard.calls == []


# ── installing ───────────────────────────────────────────────────────────────────
def _installer_env(bindir: Path, tmp_path: Path) -> dict[str, str]:
    """PATH with the guard's bindir first, and the guard's own writes confined to tmp.

    Without the HOME/LOG overrides an installer test would append its refusal to the
    developer's real ~/.digithings/az-guard-refusals.log.
    """
    return {
        "PATH": os.pathsep.join([str(bindir), os.environ["PATH"]]),
        "HOME": str(tmp_path / "installer-home"),
        "AZ_GUARD_LOG": str(tmp_path / "installer-refusals.log"),
    }


def _run_installer(*args: str, bindir: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "installer-home"
    home.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        ["bash", str(INSTALLER), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **_installer_env(bindir, tmp_path)},
    )


@pytest.mark.unit
def test_installer_links_checks_and_uninstalls(tmp_path: Path) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()

    install = _run_installer("--bindir", str(bindir), bindir=bindir, tmp_path=tmp_path)
    assert install.returncode == 0, install.stderr

    link = bindir / "az"
    assert link.is_symlink(), "the guard is installed as a symlink so `git pull` updates it"
    assert link.resolve() == SHIM.resolve()

    check = _run_installer("--bindir", str(bindir), "--check", bindir=bindir, tmp_path=tmp_path)
    assert check.returncode == 0, f"--check failed:\n{check.stdout}\n{check.stderr}"
    assert "PASS" in check.stdout

    uninstall = _run_installer(
        "--bindir", str(bindir), "--uninstall", bindir=bindir, tmp_path=tmp_path
    )
    assert uninstall.returncode == 0, uninstall.stderr
    assert not link.exists() and not link.is_symlink()


@pytest.mark.unit
def test_uninstall_leaves_a_real_az_alone(tmp_path: Path) -> None:
    """Rollback must never delete someone's Azure CLI."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    real_az = bindir / "az"
    real_az.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    result = _run_installer(
        "--bindir", str(bindir), "--uninstall", bindir=bindir, tmp_path=tmp_path
    )

    assert result.returncode != 0
    assert real_az.is_file(), "the installer deleted an az that is not its own symlink"


@pytest.mark.unit
def test_check_fails_when_a_different_az_wins_on_path(tmp_path: Path) -> None:
    """The install is not done until ``az`` actually resolves to the guard."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    (other / "az").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    install = _run_installer("--bindir", str(bindir), bindir=bindir, tmp_path=tmp_path)
    assert install.returncode == 0, install.stderr

    check = _run_installer("--bindir", str(bindir), "--check", bindir=other, tmp_path=tmp_path)
    assert check.returncode != 0
    assert "FAIL" in check.stderr


if __name__ == "__main__":  # pragma: no cover - convenience only
    sys.exit(pytest.main([__file__, "-v"]))
