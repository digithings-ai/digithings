"""Regression tests for the *name* side of scripts/check_example_credentials.py.

DIG-2266, found while verifying DIG-550. Every earlier leaf in the credential-guard
epic widened ``CRED_VALUE_PATTERNS`` - the *value* side. The *name* side never got
an entry for an AWS access key ID, so a real key on the most conventional AWS
spelling in this repo reported clean before the value was ever looked at:

    looks_cred_var('AWS_ACCESS_KEY_ID')       False  <- the gap
    looks_cred_var('AWS_ACCESS_TOKEN')       True
    looks_cred_var('AWS_API_KEY')            True
    looks_cred_var('AWS_SECRET_ACCESS_KEY')  True

``ACCESS_TOKEN`` was in the list; ``ACCESS_KEY`` was not. The value pattern
``^AKIA[A-Za-z0-9]{16,}`` added by DIG-749 would have reported that key - the name
gate simply ran first and said no. The identical value under ``AWS_ACCESS_TOKEN``
was reported, which is what proves the value was never the problem.

The contract pinned here:

  * ``ACCESS_KEY`` is a ``CRED_VAR_PATTERNS`` entry, so an AWS access key ID name
    is in scope;
  * the two gates together report a real ``AKIA`` value under that name, bare and
    behind a trailing ``# comment`` - the commented case is the one that matters,
    because a value carrying a comment never reaches the entropy score and so the
    vendor loop is the only gate that can catch it;
  * widening the list costs the tracked ``.example`` / ``.template`` corpus
    nothing. ``ACCESS_KEY`` is a substring test, so ``SSH_ACCESS_KEY_ID`` newly
    matches on the name; that widening is pinned deliberately rather than left
    implicit, and the corpus fence below is what keeps it honest.

Kept in its own file rather than added to
``test_check_example_credentials.py``, which is the pinned contract for DIG-50 and
must stay byte-identical to its committed form, and separately from
``test_check_example_credentials_vendor_prefixes.py``,
``test_check_example_credentials_commented_vendor_prefixes.py`` and
``test_check_example_credentials_short_values.py``, which are owned by earlier
leaves in this epic.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_example_credentials.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_example_credentials_under_test_access_key_names", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cec = _load_module()

#: A body AWS actually issues. The guard's ``AKIA`` rule wants 16 or more, and
#: AWS access key IDs are 20 characters in total.
AKIA_BODY = "QWERTYUIOPASDFGHJ"

#: The real key: the 4-character prefix plus the 16-character body.
AKIA_KEY = "AKIA" + AKIA_BODY

#: A trailing inline comment, as carried by a live ``KEY = ... # comment`` line.
TRAILING_COMMENT = " # rotated 2026-01"

#: The name this leaf is about: AWS's own spelling for an access key ID.
AWS_ACCESS_KEY_ID = "AWS_ACCESS_KEY_ID"


def _with_patterns(patterns):
    """Run a callable against a temporary ``CRED_VAR_PATTERNS``, then restore it.

    ``cec`` is a module-level singleton shared by every test in this file, so the
    global is put back on the way out rather than left narrowed.
    """
    saved = cec.CRED_VAR_PATTERNS

    def _run(fn):
        cec.CRED_VAR_PATTERNS = patterns
        try:
            return fn()
        finally:
            cec.CRED_VAR_PATTERNS = saved

    return _run


_without_access_key = _with_patterns(
    [p for p in cec.CRED_VAR_PATTERNS if p != "ACCESS_KEY"]
)


def _corpus_findings():
    """Every ``(file, var)`` the guard reports over the tracked example corpus.

    Mirrors ``main()``'s scan - tracked files whose name contains ``.example`` or
    ``.template``, one ``NAME=value`` line at a time, both gates required - so a
    fence on this walks exactly the set CI's ``main()`` call would report.
    """
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.splitlines()
    findings = []
    for name in tracked:
        if ".example" not in name and ".template" not in name:
            continue
        for line in (REPO_ROOT / name).read_text(errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            var, val = s.split("=", 1)
            if cec.looks_cred_var(var.strip()) and cec.looks_cred_val(val):
                findings.append((name, var.strip()))
    return findings


def test_access_key_is_a_name_pattern():
    """The gap was a missing list entry, so the list entry is what is pinned.

    Asserted against the pattern list rather than ``looks_cred_var`` alone: a name
    pattern can match by accident under some other entry, and the next test is
    what rules that out.
    """
    assert "ACCESS_KEY" in cec.CRED_VAR_PATTERNS


def test_aws_access_key_id_name_is_in_scope():
    """The name this leaf is about is now in scope, and only because of ACCESS_KEY.

    The differential half matters: it is what distinguishes this fix from a rename
    that happens to match some other entry.
    """
    assert cec.looks_cred_var(AWS_ACCESS_KEY_ID) is True
    assert _without_access_key(lambda: cec.looks_cred_var(AWS_ACCESS_KEY_ID)) is False


@pytest.mark.parametrize("suffix", ["", TRAILING_COMMENT])
def test_real_aws_key_under_that_name_is_reported(suffix: str) -> None:
    """Both gates, together, on the exact line the gap let through."""
    assert cec.looks_cred_var(AWS_ACCESS_KEY_ID) and cec.looks_cred_val(AKIA_KEY + suffix)


def test_the_control_name_was_never_the_difference():
    """The value was already a credential; only the name decided the verdict.

    This is the pair that isolates the defect. Same value, same file, same
    everything except the variable name - and the ``ACCESS_TOKEN`` spelling is
    reported today, before this leaf's change.
    """
    value = AKIA_KEY + TRAILING_COMMENT
    assert cec.looks_cred_var("AWS_ACCESS_TOKEN") and cec.looks_cred_val(value)
    assert cec.looks_cred_var(AWS_ACCESS_KEY_ID) and cec.looks_cred_val(value)


def test_aws_secret_access_key_keeps_matching_without_access_key():
    """The name the brief flagged is already covered, and must stay covered.

    ``AWS_SECRET_ACCESS_KEY`` matched on ``SECRET`` before this leaf and still does.
    Pinned so a later edit that prunes the list cannot quietly un-scope it by
    dropping ``SECRET`` and leaning on the ``ACCESS_KEY`` substring instead.
    """
    assert _without_access_key(lambda: cec.looks_cred_var("AWS_SECRET_ACCESS_KEY")) is True


def test_ssh_access_key_id_newly_matches_and_behaves_like_every_incumbent_key_name():
    """The widening ``ACCESS_KEY`` causes, stated rather than left implicit.

    ``ACCESS_KEY`` is a substring test, so ``SSH_ACCESS_KEY_ID`` newly matches on
    the name. Asserted differentially instead of by taste, because that is the only
    version of this claim worth pinning: the widened name must reach the same
    verdicts as a name that has always been in the list.

    That matters because ``SSH_ACCESS_KEY_ID=~/.ssh/id_ed25519`` - a path to a key
    file, not a credential - is *reported*. It is reported for every incumbent name
    too (``PRIVATE_KEY``, ``SSH_PRIVATE_KEY``, ``API_KEY``, ``SIGNING_KEY`` all
    report the same three paths today), so it is the value side's existing
    behaviour and not something this leaf decides. Changing it means touching
    ``CRED_MIN_VALUE_LEN`` / ``CRED_MIN_ENTROPY_LEN``, which the leaf that owns
    the short-value rules pins and this leaf must not edit.
    """
    assert cec.looks_cred_var("SSH_ACCESS_KEY_ID") is True
    assert _without_access_key(lambda: cec.looks_cred_var("SSH_ACCESS_KEY_ID")) is False
    values = (AKIA_KEY, AKIA_KEY + TRAILING_COMMENT, "~/.ssh/id_ed25519", "changeme", "", "AKIA")
    for value in values:
        widened = cec.looks_cred_var("SSH_ACCESS_KEY_ID") and cec.looks_cred_val(value)
        incumbent = cec.looks_cred_var("PRIVATE_KEY") and cec.looks_cred_val(value)
        assert widened == incumbent, (
            f"{value!r}: widened name reports {widened}, incumbent name reports {incumbent}"
        )


def test_access_key_adds_no_finding_to_the_tracked_corpus():
    """The fence: widening the name list must not move any corpus verdict.

    Measured rather than assumed, and in both directions - the corpus is empty
    with ``ACCESS_KEY`` in the list, and stays empty when it is taken back out.
    An empty corpus alone would not catch a list edit that also changed something
    else, so the equality is asserted too.
    """
    with_access_key = _corpus_findings()
    without_access_key = _without_access_key(_corpus_findings)
    assert with_access_key == [], f"ACCESS_KEY added a corpus finding: {with_access_key}"
    assert with_access_key == without_access_key


def test_no_tracked_corpus_line_names_an_access_key():
    """Why the fence above is empty: the corpus never uses this spelling at all.

    Worth pinning on its own, because it is the fact that makes this leaf safe, and
    it fails loudly if someone later commits the very line this leaf is about -
    at which point the guard has to report it, and the fence needs re-reading.
    """
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.splitlines()
    named = []
    for name in tracked:
        if ".example" not in name and ".template" not in name:
            continue
        for line in (REPO_ROOT / name).read_text(errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            if "ACCESS_KEY" in s.split("=", 1)[0].upper():
                named.append(f"{name}:{s}")
    assert named == [], f"tracked corpus now names an access key: {named}"


def test_guard_itself_is_clean_on_the_corpus():
    """``main()``'s own verdict on the tracked corpus, at the gate's own threshold.

    This is the third gate in the brief, run as a test so a regression in the fix
    shows up in the unit suite rather than only in CI.
    """
    assert cec.main() == 0