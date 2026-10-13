"""Unit tests for scripts/check_plaintext_credentials.py (DIG-179).

The guard exists because a live Proton Mail account name and password sat in
plain text in a committed chat transcript and every existing guard missed it.
So the tests assert two different things, and both matter:

1. the DIG-179 shape is rejected -- proved here against synthetic values with the
   real transcript's geometry, because the real value must never enter this file;
2. ordinary prose that merely *mentions* passwords is not rejected -- the
   sentence list below is regression material, each entry a false positive that
   actually fired when the guard was first switched on across the tree.

This file is exempt from the guard's own scan (see SELF_FILES in the script): a
test for a credential detector has to contain the credential shape to detect it.
That exemption is asserted to still be narrow in `test_skip_list_stays_narrow`.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_plaintext_credentials.py"


def _load() -> object:
    spec = importlib.util.spec_from_file_location(
        "check_plaintext_credentials", _SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard() -> object:
    return _load()


# Synthetic stand-ins. Same geometry as the real transcript (an address on a
# private-mail domain with a bare token beside it; a passphrase with no separator
# after the label) so the rules are exercised, without the real value. The domain
# is a real provider because the rule matches a fixed domain list, so the local
# part is deliberately invented rather than copied from the incident.
SYNTHETIC_ADDRESS = "digithings-guard-test@protonmail.com"
SYNTHETIC_BARE_TOKEN = "Kt4pWq82zx"
SYNTHETIC_PASSPHRASE = "cobalt lantern harbour trellis"


def _rules(guard: object, text: str) -> set[str]:
    return {rule_id for _, rule_id, _ in guard.scan_text(text)}


# ── the DIG-179 shapes are caught ────────────────────────────────────────────


@pytest.mark.unit
def test_mailbox_account_with_bare_token_is_flagged(guard: object) -> None:
    line = f"[17:56] Client: {SYNTHETIC_ADDRESS} {SYNTHETIC_BARE_TOKEN}"
    assert _rules(guard, line) == {"mailbox-account"}


@pytest.mark.unit
def test_password_label_with_bare_separator_passphrase_is_flagged(guard: object) -> None:
    line = f"[18:19] Chris: Thx! Le user password {SYNTHETIC_PASSPHRASE}"
    assert _rules(guard, line) == {"password-label"}


@pytest.mark.unit
def test_password_label_with_equals_separator_is_flagged(guard: object) -> None:
    line = f"password={SYNTHETIC_PASSPHRASE}"
    assert _rules(guard, line) == {"password-label"}


@pytest.mark.unit
def test_proton_domain_is_covered_because_that_was_the_incident(
    guard: object,
) -> None:
    line = f"login mailbox.r4@protonmail.com {SYNTHETIC_BARE_TOKEN}"
    assert _rules(guard, line) == {"mailbox-account"}


@pytest.mark.unit
def test_finding_carries_line_number_and_rule_but_never_the_value(
    guard: object,
) -> None:
    text = (
        "[17:56] Client: "
        f"{SYNTHETIC_ADDRESS} {SYNTHETIC_BARE_TOKEN}\n"
        f"[18:19] Chris: password {SYNTHETIC_PASSPHRASE}\n"
    )
    findings = guard.scan_text(text)
    assert [(lineno, rule_id) for lineno, rule_id, _ in findings] == [
        (1, "mailbox-account"),
        (2, "password-label"),
    ]
    rendered = repr(findings)
    assert SYNTHETIC_BARE_TOKEN not in rendered
    assert SYNTHETIC_PASSPHRASE not in rendered


# ── the redacted form that is now in the tree must stay clean ────────────────


@pytest.mark.unit
def test_redacted_transcript_is_clean(guard: object) -> None:
    text = (
        "[17:56] Client: "
        f"{SYNTHETIC_ADDRESS} [REDACTED DIG-179]\n"
        "[18:19] Chris: Thx! Le user password [REDACTED DIG-179]\n"
    )
    assert guard.scan_text(text) == []


@pytest.mark.unit
def test_redaction_marker_wins_even_without_a_value(guard: object) -> None:
    assert guard.scan_text("password [REDACTED]") == []
    assert guard.scan_text("password <your-password-here>") == []
    assert guard.scan_text("password ${PROTON_PASSWORD}") == []
    assert guard.scan_text("password $PROTON_PASSWORD") == []


# ── regression material: prose that fired false positives ────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "line",
    [
        # "pass" is an English verb. Excluding bare `pass` from the label set is
        # what keeps these four out.
        "Bucket threads by last activity. Callers should pass threads already sorted",
        "const ok = pass is guaranteed (useMotionSafe flips `mounted` one tick after mount)",
        'pass = "env(SENDGRID_API_KEY)"',
        "# Olympus Dashboard - Second-Pass Redesign (Design Spec)",
        # A label glued to another word is a compound, not a value.
        "**Auth - leaked-password protection (Hibp)**: accepted / plan-gated residual",
        # An enumeration of key names, not a passphrase.
        "keys whose names contain ``password|api_key|token|secret``; it does not recurse",
        # A minified JSON blob that happens to contain a query string.
        '{"expected_ticket_ids":[2,4],"query":"expired portal login"}',
        # Real doc sentences: label, copula, then English.
        "a password manager cannot express machine access",
        "the password is stored in Bitwarden, never in a file",
        "passwords are rotated every 90 days by Security",
        # Source code: assignment labels are the sibling guard's lane, not ours.
        "const apiKey = await resolveApiKey(request)",
        "const token = session.access_token",
    ],
)
def test_prose_and_source_lines_are_not_flagged(guard: object, line: str) -> None:
    assert guard.scan_text(line) == []


@pytest.mark.unit
def test_single_english_word_after_label_is_not_a_credential(guard: object) -> None:
    # A one-word value is a sentence fragment, never the DIG-179 passphrase.
    assert guard.scan_text("password forgotten") == []


# ── the guard is non-vacuous and honest about itself ─────────────────────────


@pytest.mark.unit
def test_scan_text_never_returns_the_value(guard: object) -> None:
    text = f"{SYNTHETIC_ADDRESS} {SYNTHETIC_BARE_TOKEN}"
    for lineno, rule_id, reason in guard.scan_text(text):
        assert isinstance(lineno, int)
        assert rule_id in {"mailbox-account", "password-label"}
        assert reason == "credential"


@pytest.mark.unit
def test_skip_list_stays_narrow(guard: object) -> None:
    # The guard's own source and test are exempt because they must contain the
    # shape. Nothing else in scripts/ or tests/ may be.
    assert guard.SELF_FILES == frozenset(
        {
            "scripts/check_plaintext_credentials.py",
            "tests/scripts/test_check_plaintext_credentials.py",
        }
    )
    assert guard.UNEXPECTED_SKIPS == frozenset()


@pytest.mark.unit
def test_allowlist_is_small_and_every_entry_is_reasoned(guard: object) -> None:
    problems = guard._assert_allowlist_is_reviewed()
    assert problems == []
    assert len(guard.ALLOWLIST) <= guard.ALLOWLIST_CAP


@pytest.mark.unit
def test_skip_and_allowlist_checks_pass_on_this_checkout(guard: object) -> None:
    assert guard._assert_skip_list_is_tight() == []


# ── CLI, end to end ──────────────────────────────────────────────────────────


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


@pytest.mark.unit
def test_cli_exits_nonzero_on_a_credential_and_prints_no_value(
    guard: object, tmp_path: Path
) -> None:
    (tmp_path / "chat.txt").write_text(
        f"[17:56] Client: {SYNTHETIC_ADDRESS} {SYNTHETIC_BARE_TOKEN}\n"
    )
    result = _run(tmp_path, "chat.txt")
    assert result.returncode == 1
    assert "chat.txt:1 mailbox-account" in result.stderr
    assert SYNTHETIC_BARE_TOKEN not in result.stdout + result.stderr


@pytest.mark.unit
def test_cli_exits_zero_on_a_clean_tree(guard: object, tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text(
        "The password lives in the secret store. Rotations run every 90 days.\n"
    )
    result = _run(tmp_path, "readme.md")
    assert result.returncode == 0
    assert "OK" in result.stdout


@pytest.mark.unit
def test_allowlist_suppresses_exactly_one_location(guard: object) -> None:
    rel = "scripts/rls_proof/00_supabase_shim.sql"
    text = "  CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'rls_proof_local';\n"
    assert guard.findings_for(rel, text) != []

    guard.ALLOWLIST[f"{rel}:1"] = "test-only stand-in"
    try:
        assert guard.findings_for(rel, text) == []
        # The exemption is per location: a second hit in the same file is still
        # reported, so an allowlist entry cannot become a whole-file waiver.
        assert guard.findings_for(rel, text * 3) != []
        # And it does not leak into another file.
        assert guard.findings_for("scripts/other.sql", text) != []
    finally:
        del guard.ALLOWLIST[f"{rel}:1"]


@pytest.mark.unit
def test_shipped_allowlist_entry_matches_the_repository(
    guard: object,
) -> None:
    # The allowlist is keyed on path:line, so a moved line silently stops
    # suppressing and starts failing the build. That is the intended direction of
    # failure, but the shipped entry must still point at a real finding today.
    for location, _reason in guard.ALLOWLIST.items():
        rel, _, lineno = location.rpartition(":")
        target = _REPO_ROOT / rel
        assert target.is_file(), f"allowlist points at a missing file: {rel}"
        line = target.read_text(errors="replace").splitlines()[int(lineno) - 1]
        assert guard.scan_text(line), f"allowlist entry no longer matches: {location}"


@pytest.mark.unit
def test_cli_does_not_scan_binary_files(guard: object, tmp_path: Path) -> None:
    (tmp_path / "blob.bin").write_bytes(
        b"\x00\x01password\xc0\xfe\xb1 leaked bytes\x00"
    )
    result = _run(tmp_path, "blob.bin")
    assert result.returncode == 0, result.stderr


@pytest.mark.unit
def test_cli_reports_nothing_to_scan_instead_of_ok(
    guard: object, tmp_path: Path
) -> None:
    # A leak guard that reads zero files and prints OK is a false green: it
    # turns a missing scan into a passing build. Refuse to certify it.
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run(empty)
    assert result.returncode == 2
    assert "OK" not in result.stdout
    assert "no files to scan" in result.stderr


@pytest.mark.unit
def test_cli_scans_when_root_is_a_subdirectory_of_a_repo(
    guard: object, tmp_path: Path
) -> None:
    # Regression, DIG-179: `git ls-files` prints repo-root-relative paths, so the
    # original implementation joined them onto --root, built paths that did not
    # exist, read zero files and printed OK on a tree that still held the
    # credential. A subdirectory is the only shape in which that happens, so the
    # test uses one.
    repo = tmp_path / "repo"
    nested = repo / "clients" / "chats"
    nested.mkdir(parents=True)
    (nested / "2026-05-28.txt").write_text(
        f"[17:56] Client: {SYNTHETIC_ADDRESS} {SYNTHETIC_BARE_TOKEN}\n"
    )
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    result = _run(nested)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "mailbox-account" in result.stderr


@pytest.mark.unit
def test_tracked_files_matches_the_repo_toplevel(guard: object, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "chat.txt").write_text("nothing to see\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    from_root = [p.name for p in guard.tracked_files(repo)]
    from_nested = [p.name for p in guard.tracked_files(nested)]
    assert from_nested == from_root == ["chat.txt"]