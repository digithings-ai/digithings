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

``ACCESS_KEY`` rather than the vendor-prefixed ``AWS_ACCESS_KEY``, so the entry also
covers ``R2_ACCESS_KEY_ID`` - the live spelling, read by ten ``secrets`` uses across
five workflows. The retired ``CHECKPOINT_ARCHIVE_R2_ACCESS_KEY`` spelling is not
cited: ``tests/scripts/test_checkpoint_archive_workflow.py`` and
``tests/dq/ops/test_checkpoint_archive.py`` both assert it is gone.

The contract pinned here:

  * ``ACCESS_KEY`` is a ``CRED_VAR_PATTERNS`` entry, so an AWS access key ID name is
    in scope;
  * the two gates together report a real ``AKIA`` value under that name, bare and
    behind a trailing ``# comment`` - the commented case is the one that matters,
    because a value carrying a comment never reaches the entropy score and so the
    vendor loop is the only gate that can catch it;
  * the widening the substring form causes is pinned *by its boundary*, not left
    implicit: the names it newly claims, and the neighbouring names it must not;
  * widening the list costs the tracked ``.example`` / ``.template`` corpus nothing.

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

#: A 16-character body. ``^AKIA[A-Za-z0-9]{16,}`` wants 16 or more after the prefix;
#: a real AWS access key ID is 20 characters in total. Hand-typed, not a live key.
AKIA_BODY = "QWERTYUIOPASDFGHJ"

#: The whole value: the 4-character prefix plus the body.
AKIA_KEY = "AKIA" + AKIA_BODY

#: A trailing inline comment, as carried by a live ``KEY = ... # comment`` line.
TRAILING_COMMENT = " # rotated 2026-01"

#: A path to a key file rather than a key. Used below for the widening discussion.
SSH_KEY_PATH = "~/.ssh/id_ed25519"

#: The name this leaf is about: AWS's own spelling for an access key ID.
AWS_ACCESS_KEY_ID = "AWS_ACCESS_KEY_ID"


def _run_with(patterns):
    """Return a callable that runs ``fn`` against a temporary ``CRED_VAR_PATTERNS``.

    ``cec`` is a module-level singleton shared by every test in this file, so the
    global is read at call time and put back on the way out rather than left
    narrowed. Reading it at call time (not at decoration time) means a test that
    narrows the list itself is restored to *its* starting value, not to whatever the
    list held when this helper was built.
    """

    def _call(fn):
        saved = cec.CRED_VAR_PATTERNS
        cec.CRED_VAR_PATTERNS = patterns
        try:
            return fn()
        finally:
            cec.CRED_VAR_PATTERNS = saved

    return _call


def _without_access_key():
    """``_run_with`` against the name list with this leaf's entry taken back out."""
    return _run_with([p for p in cec.CRED_VAR_PATTERNS if p != "ACCESS_KEY"])


def _corpus_assignable_lines():
    """Every ``(file, var, value)`` line ``main()``'s scan considers.

    Mirrors ``main()``: tracked files whose name contains ``.example`` or
    ``.template``, one ``NAME=value`` line at a time, comment lines and lines without
    an ``=`` skipped. Both gates are applied by the caller, so a fence on this walks
    the same candidates the guard's own ``main()`` call would.

    The scan is anchored on ``REPO_ROOT`` rather than the process CWD, because
    ``git ls-files`` is CWD-relative: run from anywhere else it reports a different,
    possibly empty, file set.
    """
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.splitlines()
    lines = []
    for name in tracked:
        if ".example" not in name and ".template" not in name:
            continue
        try:
            body = (REPO_ROOT / name).read_text(errors="replace")
        except OSError:
            continue
        for line in body.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            var, val = s.split("=", 1)
            lines.append((name, var.strip(), val))
    return lines


def _corpus_findings():
    """The ``(file, var)`` pairs the guard reports over the corpus, both gates on."""
    return [
        (name, var)
        for name, var, val in _corpus_assignable_lines()
        if cec.looks_cred_var(var) and cec.looks_cred_val(val)
    ]


#: Names that contain ``ACCESS_KEY`` and were out of scope before this leaf.
#: ``AWS_ACCESS_KEY`` is the nearest neighbour of the leaf's own subject and
#: ``R2_ACCESS_KEY_ID`` is the live spelling this repo actually reads - both are
#: pinned so the comment in the script cannot drift away from the code. The last two
#: are the neighbours the substring form most plausibly over-reaches on.
NEWLY_MATCHED_NAMES = [
    AWS_ACCESS_KEY_ID,
    "AWS_ACCESS_KEY",
    "R2_ACCESS_KEY_ID",
    "SSH_ACCESS_KEY_ID",
    "SSH_ACCESS_KEY_FILE",
    "GPG_ACCESS_KEY",
]

#: Neighbouring names that must *not* be dragged in. The first three are the ones
#: that only point at a key; the last three are unrelated identifiers of about the
#: same shape. ``ACCESS_KEY`` is a substring test, so this is the boundary that
#: decides whether the widening is acceptable.
NAMES_THAT_MUST_NOT_MATCH = [
    "AWS_ACCOUNT_ID",
    "AWS_KEY_ALIAS",
    "AWS_KEY_COUNT",
    "MONGO_DB_URI",
    "KEYSTORE_PATH",
    "SSH_AUTH_SOCK",
]


def test_access_key_is_a_name_pattern():
    """The gap was a missing list entry, so the list entry is what is pinned.

    Asserted against the pattern list rather than ``looks_cred_var`` alone: a name
    pattern can match by accident under some other entry, and the next tests are
    what rule that out.
    """
    assert "ACCESS_KEY" in cec.CRED_VAR_PATTERNS


def test_the_leaf_name_is_in_scope_and_only_because_of_access_key():
    """The name this leaf is about is now in scope, and the cause is pinned too.

    The differential half matters: it is what distinguishes this fix from a rename
    that happens to match some other entry.
    """
    assert cec.looks_cred_var(AWS_ACCESS_KEY_ID) is True
    assert _without_access_key()(lambda: cec.looks_cred_var(AWS_ACCESS_KEY_ID)) is False


@pytest.mark.parametrize("name", NEWLY_MATCHED_NAMES)
def test_name_is_newly_matched_by_access_key(name: str) -> None:
    """Each name ``ACCESS_KEY`` newly claims is claimed because of ``ACCESS_KEY``.

    The substring form does not stop at AWS. ``SSH_ACCESS_KEY_FILE`` and
    ``GPG_ACCESS_KEY`` are the two it is most likely to over-reach on, so they are
    pinned here rather than left to be discovered later.
    """
    assert cec.looks_cred_var(name) is True
    assert _without_access_key()(lambda: cec.looks_cred_var(name)) is False


@pytest.mark.parametrize("name", NAMES_THAT_MUST_NOT_MATCH)
def test_neighbouring_names_are_not_dragged_in(name: str) -> None:
    """The other side of the boundary: names the widening must leave alone.

    Three of these only *point* at a key (``AWS_KEY_ALIAS`` is a label,
    ``AWS_KEY_COUNT`` a count, ``AWS_ACCOUNT_ID`` an account), and an account id is
    not a credential. If a future edit to ``CRED_VAR_PATTERNS`` widens the list
    far enough to claim them, the widening has gone past what this leaf measured.
    """
    assert cec.looks_cred_var(name) is False


@pytest.mark.parametrize("suffix", ["", TRAILING_COMMENT])
def test_real_aws_key_under_that_name_is_reported(suffix: str) -> None:
    """Both gates, together, on the exact line the gap let through.

    Two assertions rather than one conjunction, so a failure says which gate
    stopped matching.
    """
    assert cec.looks_cred_var(AWS_ACCESS_KEY_ID) is True
    assert cec.looks_cred_val(AKIA_KEY + suffix) is True


def test_the_value_passed_before_this_leaf_and_the_name_did_not():
    """The pair that isolates the defect: same value, only the name differs.

    With the value taken out of scope along with the name, the value still passes
    ``looks_cred_val`` - including the commented form, which never reaches the
    entropy score. So the value was never the problem, and the identical value under
    a name that has always been in the list was already reported.
    """
    for value in (AKIA_KEY, AKIA_KEY + TRAILING_COMMENT):
        assert _without_access_key()(lambda: cec.looks_cred_var(AWS_ACCESS_KEY_ID)) is False
        # No `_without_access_key()` wrapper here: `looks_cred_val` reads only
        # `CRED_VALUE_PATTERNS`, so narrowing the name list around it would be
        # decoration that reads as if it were doing work.
        assert cec.looks_cred_val(value) is True
        assert cec.looks_cred_var("AWS_ACCESS_TOKEN") is True
        assert cec.looks_cred_val(value) is True


def test_aws_secret_access_key_keeps_matching_without_access_key():
    """The name the brief flagged is already covered, and must stay covered.

    ``AWS_SECRET_ACCESS_KEY`` matched on ``SECRET`` before this leaf and still does.
    Pinned so a later edit that prunes the list cannot quietly un-scope it by
    dropping ``SECRET`` and leaning on the ``ACCESS_KEY`` substring instead.
    """
    assert _without_access_key()(lambda: cec.looks_cred_var("AWS_SECRET_ACCESS_KEY")) is True


def test_the_key_path_reported_under_a_newly_matched_name_is_shared_with_every_incumbent():
    """Why ``SSH_ACCESS_KEY_ID`` reporting a key *path* is not new behaviour.

    ``ACCESS_KEY`` is a substring test, so ``SSH_ACCESS_KEY_ID`` newly matches on the
    name, and a path to a key file is therefore reported under it. That is the value
    side's doing, not this leaf's: the name side can only switch a verdict *off* for a
    name that does not match, and every incumbent key name matches today. So the verdict
    is pinned where it is actually made - on the value - with the incumbent name matches
    pinned alongside it.

    Reported today under the incumbents as well; changing that means touching
    ``CRED_MIN_VALUE_LEN`` / ``CRED_MIN_ENTROPY_LEN``, which the leaf that owns the
    short-value rules pins and this leaf must not edit.
    """
    assert cec.looks_cred_val(SSH_KEY_PATH) is True
    for incumbent in ("PRIVATE_KEY", "SSH_PRIVATE_KEY", "API_KEY", "SIGNING_KEY"):
        assert cec.looks_cred_var(incumbent) is True


def test_access_key_adds_no_finding_to_the_tracked_corpus():
    """The fence: widening the name list must not move any corpus verdict.

    Measured, not assumed, and in both directions. The corpus is empty with
    ``ACCESS_KEY`` in the list *and* stays empty when it is taken back out - the
    equality is the forward-looking half: it holds even once the corpus gains
    findings, where an empty-set check alone would stop distinguishing anything.
    """
    with_access_key = _corpus_findings()
    assert with_access_key == [], f"ACCESS_KEY added a corpus finding: {with_access_key}"
    assert with_access_key == _without_access_key()(_corpus_findings)


def test_the_corpus_scan_actually_covers_the_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fence above is worthless over an empty scan, so the scan is pinned.

    ``main()`` calls ``git ls-files`` without a ``cwd``, so it reports whatever the
    process CWD happens to be. Run from ``tests/scripts/`` it sees 103 files and none
    of them is an ``.example`` / ``.template``, and prints ``OK`` over nothing. This
    test pins that the corpus is non-empty - so a fence or a ``main()`` call reading
    an empty file set fails loudly instead of passing - and then that the anchored
    scan and the CWD-relative one agree once the CWD is the repo root. That second
    assertion is what fails if the ``chdir`` below is ever dropped, which is the whole
    point of having it: ``main()`` keeps returning 0 over nothing either way.
    """
    candidates = _corpus_assignable_lines()
    assert candidates, "the tracked .example / .template corpus has no assignable lines"

    anchored = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, stdout=subprocess.PIPE, text=True, check=True
    ).stdout.splitlines()

    monkeypatch.chdir(REPO_ROOT)
    from_cwd = subprocess.run(
        ["git", "ls-files"], stdout=subprocess.PIPE, text=True, check=True
    ).stdout.splitlines()
    assert from_cwd == anchored


def test_guard_itself_is_clean_on_the_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    """``main()``'s own verdict on the tracked corpus, at the gate's own threshold.

    This is the third gate in the brief, run as a test so a regression in the fix
    shows up in the unit suite rather than only in CI.

    ``chdir`` is not optional: ``main()`` resolves both ``git ls-files`` and the
    tracked paths against the process CWD, so from anywhere else it scans a
    different - possibly empty - file set and returns 0 without having looked at
    anything. Matches how the sibling short-value leaf pins the same call.
    """
    monkeypatch.chdir(REPO_ROOT)
    assert cec.main() == 0