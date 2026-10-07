"""`ACCESS_KEY` belongs in `CRED_VAR_PATTERNS`: an AWS access key id is a credential.

The defect
----------
`scripts/check_example_credentials.py` reports a line only when two independent
tests agree: the *name* matches `CRED_VAR_PATTERNS` (`looks_cred_var`) and the
*value* matches `CRED_VALUE_PATTERNS` or clears the entropy floor
(`looks_cred_val`). Every earlier leaf in this epic widened the value side. The
name side carried `ACCESS_TOKEN` but not `ACCESS_KEY`, so the most conventional
AWS spelling was out of scope before the value was ever looked at - even though
the value pattern `^AKIA[A-Za-z0-9]{16,}` would have reported it.

Measured on `feat/50-credential-guard-shape` at `9e6a0963e`::

    looks_cred_var('AWS_ACCESS_KEY_ID')      -> False   <- the gap
    looks_cred_var('AWS_ACCESS_TOKEN')      -> True
    looks_cred_var('AWS_API_KEY')           -> True
    looks_cred_var('AWS_SECRET_ACCESS_KEY') -> True    (on `SECRET`)

End to end, through `main()` on a tracked `.example` file, five credential-named
lines reported and `AWS_ACCESS_KEY_ID=AKIA<17 chars>` did not. Renaming that same
line to `AWS_ACCESS_TOKEN` made the identical value report, which locates the
defect on the name side exactly.

The contract pinned here
------------------------
`looks_cred_var` is True for every name that spells out an access key, and
`looks_cred_val` is True for the same AWS value under those names - bare and with
a trailing comment - so the pair reports the line. The names that name an access
key *without* carrying one (`AWS_ACCOUNT_ID`, `AWS_KEY_ALIAS`, `MONGO_ACCESS_URL`)
stay out of scope, placeholder values under an access-key name stay clean, and
the tracked `.example` / `.template` corpus stays clean.

Why this file is separate
-------------------------
`tests/scripts/test_check_example_credentials.py` is pinned byte-for-byte at
`139ad2007`, and `test_check_example_credentials_vendor_prefixes.py`,
`test_check_example_credentials_commented_vendor_prefixes.py` and
`test_check_example_credentials_short_values.py` belong to earlier leaves. Kept in
its own file so it cannot conflict with those contracts. Implementers must not
edit those, or this one.

Two of the assertions here are deliberately corpus-sensitive and will fail the
day the corpus changes: `test_no_tracked_line_name_contains_access_key_today`
(pins the measured zero that justifies the pattern) and
`test_the_corpus_fence_is_not_vacuous` (stops `main() == 0` from passing because
nothing was scanned). Both failing means the corpus moved and the reasoning has
to be re-measured, not that the pattern is wrong.

Every value below is **synthetic**. It was built by hand to satisfy the value
patterns and thresholds under test. No value was taken from git history and none
is a real key.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_example_credentials_aws_access_key_name", REPO_ROOT / "scripts" / "check_example_credentials.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cec = _load_module()
pytestmark = pytest.mark.unit

#: A synthetic 16-character body. `AKIA` plus this body is 20 characters, the real
#: length of an AWS access key id, and 16 is the shortest body the `AKIA` value
#: pattern accepts (`{16,}`). A shorter body would silently fall off the vendor
#: pattern and let these tests measure the entropy path instead, which is a
#: different question - hence the length is asserted in its own test.
KEY_BODY = "H4n7QpR2tV9xL3cZ"

#: The AWS value, bare and with the trailing comment a `.env.example` line usually
#: carries. Both forms must report once the name is in scope.
AWS_KEY = "AKIA" + KEY_BODY
AWS_KEY_COMMENTED = AWS_KEY + "  # rotated 2026-01"

#: The same key under a temporary-credential prefix, to keep the claim about
#: `ACCESS_KEY` from being read as AWS-only.
STS_KEY = "ASIA" + KEY_BODY

#: Names that carry an access key under a spelling `ACCESS_TOKEN` cannot reach.
#: `ACCESS_KEY` is a substring test, so each of these is in scope for one reason
#: only: the literal `ACCESS_KEY` sits inside the name.
ACCESS_KEY_NAMES = [
    ("aws_access_key_id", "AWS_ACCESS_KEY_ID"),
    ("aws_access_key", "AWS_ACCESS_KEY"),
    ("azure_storage_access_key", "AZURE_STORAGE_ACCESS_KEY"),
    ("mongo_access_key", "MONGO_ACCESS_KEY"),
    ("public_access_key_id", "PUBLIC_ACCESS_KEY_ID"),
    ("ssh_access_key_id", "SSH_ACCESS_KEY_ID"),
]

#: `CRED_VAR_PATTERNS` exactly as it stood at `9e6a0963e`, before this leaf. Kept
#: as a literal so the record of what was missing cannot drift with the module, and
#: so each name below is provably unreachable without `ACCESS_KEY`.
PATTERNS_BEFORE_THIS_LEAF = [
    r'API_KEY', r'SECRET', r'TOKEN', r'PASSWORD', r'PRIVATE_KEY',
    r'CLIENT_SECRET', r'ACCESS_TOKEN', r'REFRESH_TOKEN',
    r'WEBHOOK_SECRET', r'SIGNING_KEY',
]

#: Names already in scope through another entry. Control group: they must stay in
#: scope, and `AWS_SECRET_ACCESS_KEY` shows the overlap - it already matched on
#: `SECRET`, so `ACCESS_KEY` widens the net without displacing anything.
ALREADY_IN_SCOPE_NAMES = [
    ("api_key", "AWS_API_KEY"),
    ("secret", "AWS_SECRET_ACCESS_KEY"),
    ("access_token", "AWS_ACCESS_TOKEN"),
    ("token", "AWS_SESSION_TOKEN"),
]

#: Names that name an access key without carrying one, or that merely look like
#: they do. None contains `ACCESS_KEY`, so none may be pulled into scope.
OUT_OF_SCOPE_NAMES = [
    ("account_id", "AWS_ACCOUNT_ID"),
    ("kms_key_alias", "AWS_KEY_ALIAS"),
    ("key_count", "AWS_KEY_COUNT"),
    ("access_url", "MONGO_ACCESS_URL"),
    ("key_reference", "AWS_KEY_REFERENCE"),
]

#: Values a developer writes under an access-key name that are not credentials.
PLACEHOLDER_VALUES = [
    ("empty", ""),
    ("angle brackets", "<your-access-key>"),
    ("leading placeholder word", "your-access-key-here"),
    ("change me", "changeme"),
    ("replace me", "replace-me"),
    ("test key", "test-access-key"),
    ("bare example word", "example"),
    ("short value", "AKIA123"),
    ("prose comment", "# ask ops for the account access key"),
    ("inline comment", "  # rotated 2026-01, do not commit"),
]


def _ids(rows):
    """Parametrised ids from the label column of a (label, value) probe table."""
    return [label for label, _ in rows]


def test_the_synthetic_body_is_the_length_the_value_pattern_needs():
    """Falsification control for the fixture: a short body would change the test."""
    assert len(KEY_BODY) == 16, (
        f"KEY_BODY is {len(KEY_BODY)} characters; the AKIA value pattern needs at "
        "least 16, or these tests would measure the entropy path instead"
    )
    assert len(AWS_KEY) == 20, f"AWS_KEY is {len(AWS_KEY)} characters, expected 20"


def test_access_key_is_in_the_cred_var_pattern_list():
    assert 'ACCESS_KEY' in cec.CRED_VAR_PATTERNS, (
        "CRED_VAR_PATTERNS has no ACCESS_KEY entry, so every access-key name is out "
        f"of scope; the list is {cec.CRED_VAR_PATTERNS}"
    )


def test_the_new_entry_is_a_plain_substring():
    """No anchors and no metacharacters: `looks_cred_var` tests `p in var.upper()`."""
    entries = [p for p in cec.CRED_VAR_PATTERNS if p == r'ACCESS_KEY']
    assert entries, f"CRED_VAR_PATTERNS holds no bare ACCESS_KEY entry: {cec.CRED_VAR_PATTERNS}"
    entry = entries[0]
    assert not any(c in entry for c in '$^.*+?[](){}|\\'), (
        f"{entry!r} carries regex metacharacters, which `p in var.upper()` never applies"
    )


@pytest.mark.parametrize(("label", "name"), ACCESS_KEY_NAMES, ids=_ids(ACCESS_KEY_NAMES))
def test_access_key_names_are_in_scope(label, name):
    assert cec.looks_cred_var(name), (
        f"{name} ({label}) carries an access key but the name side does not match, "
        "so the value is never examined"
    )


@pytest.mark.parametrize(("label", "name"), ACCESS_KEY_NAMES, ids=_ids(ACCESS_KEY_NAMES))
def test_no_entry_before_this_leaf_reached_these_names(label, name):
    """The gap, stated against the list as it was: only `ACCESS_KEY` closes it."""
    matched = [p for p in PATTERNS_BEFORE_THIS_LEAF if p in name.upper()]
    assert matched == [], (
        f"{name} ({label}) already matched {matched}, so it was not the gap this "
        "leaf closes; re-measure before trusting the reasoning in the docstring"
    )


@pytest.mark.parametrize(("label", "name"), ACCESS_KEY_NAMES, ids=_ids(ACCESS_KEY_NAMES))
def test_the_value_side_already_reports_the_aws_key(label, name):
    """The value was never the problem - this is the line `ACCESS_TOKEN` missed."""
    assert cec.looks_cred_val(AWS_KEY), (
        f"{name} ({label}): the AKIA value does not report on its own, so this leaf "
        "is not a name-side-only fix"
    )
    assert cec.looks_cred_val(AWS_KEY_COMMENTED), (
        f"{name} ({label}): the commented AKIA value does not report, so the "
        "trailing-comment case needs a value-side change as well"
    )


@pytest.mark.parametrize(("label", "name"), ACCESS_KEY_NAMES, ids=_ids(ACCESS_KEY_NAMES))
def test_the_pair_reports_the_line(label, name):
    assert cec.looks_cred_var(name) and cec.looks_cred_val(AWS_KEY), (
        f"{name} ({label}) must report on both sides for main() to flag it"
    )


def test_the_temporary_credential_prefix_reports_too():
    assert cec.looks_cred_val(STS_KEY), "the ASIA prefix must report on the value side"
    assert cec.looks_cred_var("AWS_ACCESS_KEY_ID") and cec.looks_cred_val(STS_KEY), (
        "an STS key under AWS_ACCESS_KEY_ID must report on both sides"
    )


@pytest.mark.parametrize(("label", "name"), ALREADY_IN_SCOPE_NAMES, ids=_ids(ALREADY_IN_SCOPE_NAMES))
def test_names_already_in_scope_stay_in_scope(label, name):
    """Control group, and the overlap check: `AWS_SECRET_ACCESS_KEY` matches `SECRET`."""
    assert cec.looks_cred_var(name), f"{name} ({label}) was in scope before this leaf and must stay there"
    matched = [p for p in PATTERNS_BEFORE_THIS_LEAF if p in name.upper()]
    assert matched, f"{name} ({label}) must match an earlier entry, not only ACCESS_KEY"


@pytest.mark.parametrize(("label", "name"), OUT_OF_SCOPE_NAMES, ids=_ids(OUT_OF_SCOPE_NAMES))
def test_names_that_name_a_key_without_carrying_one_stay_out_of_scope(label, name):
    assert not cec.looks_cred_var(name), (
        f"{name} ({label}) names a key or an id but is not key material; pulling it "
        "into scope would report on metadata"
    )


@pytest.mark.parametrize("value_label,value", PLACEHOLDER_VALUES, ids=_ids(PLACEHOLDER_VALUES))
@pytest.mark.parametrize("name", ["AWS_ACCESS_KEY_ID", "AZURE_STORAGE_ACCESS_KEY"])
def test_placeholder_values_under_an_access_key_name_stay_clean(name, value_label, value):
    assert not cec.looks_cred_val(value), (
        f"{name}={value!r} ({value_label}) must stay a placeholder, not a report"
    )


def _tracked_corpus_lines():
    tracked = subprocess.run(
        ['git', 'ls-files'], cwd=REPO_ROOT, stdout=subprocess.PIPE, text=True, check=True
    ).stdout.splitlines()
    files = [Path(f) for f in tracked if '.example' in f or '.template' in f]
    lines = []
    for f in files:
        try:
            for line in f.read_text(errors='replace').splitlines():
                s = line.strip()
                if not s or s.startswith('#') or '=' not in s:
                    continue
                lines.append((f.name, s.split('=', 1)[0].strip()))
        except Exception:
            continue
    return files, lines


def test_no_tracked_line_name_contains_access_key_today():
    """The measured zero that justifies the pattern: no false positive exists today."""
    _, lines = _tracked_corpus_lines()
    offenders = sorted({name for _, name in lines if 'ACCESS_KEY' in name.upper()})
    assert offenders == [], (
        f"the tracked corpus now names an access key: {offenders}. Re-measure - "
        "`main()` staying clean now rests on the value side alone"
    )


def test_the_corpus_fence_is_not_vacuous():
    """`main() == 0` only means something if the corpus has credential-named lines."""
    files, lines = _tracked_corpus_lines()
    assert len(files) >= 10, f"expected a real .example/.template corpus, found {len(files)} files"
    named = sorted({name for _, name in lines if cec.looks_cred_var(name)})
    assert len(named) >= 10, (
        f"only {len(named)} tracked lines match the name side ({named}); the corpus "
        "fence would pass vacuously"
    )


def test_tracked_example_files_stay_clean():
    """The false-positive fence for the whole tracked `.example`/`.template` corpus."""
    cwd = Path.cwd()
    try:
        import os

        os.chdir(REPO_ROOT)
        assert cec.main() == 0
    finally:
        os.chdir(cwd)


@pytest.fixture
def probe_repo(tmp_path):
    """A throwaway git repo whose only tracked file is a `.env.example` probe."""
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    (tmp_path / '.env.example').write_text(
        "\n".join([
            "# a synthetic probe, every value hand-made",
            "AWS_ACCESS_KEY_ID=" + AWS_KEY_COMMENTED,
            "AWS_ACCESS_TOKEN=" + AWS_KEY,
            "AZURE_STORAGE_ACCESS_KEY=" + AWS_KEY,
            "SSH_ACCESS_KEY_ID=" + AWS_KEY,
            "AWS_ACCOUNT_ID=123456789012",
            "AWS_ACCESS_KEY_ID=<your-access-key-id>",
            "AWS_ACCESS_KEY_ID=",
            "AWS_ACCESS_KEY_ID=# ask ops for the account key",
            "",
        ])
    )
    subprocess.run(['git', 'add', '-A'], cwd=tmp_path, check=True)
    return tmp_path


def test_end_to_end_reports_the_access_key_lines(probe_repo, monkeypatch, capsys):
    """main() must flag the three access-key lines and stay quiet on the placeholders."""
    monkeypatch.chdir(probe_repo)
    assert cec.main() == 1
    err = capsys.readouterr().err
    for expected in [
        ".env.example:AWS_ACCESS_KEY_ID",
        ".env.example:AZURE_STORAGE_ACCESS_KEY",
        ".env.example:SSH_ACCESS_KEY_ID",
        ".env.example:AWS_ACCESS_TOKEN",
    ]:
        assert expected in err, f"{expected} was not reported; stderr was:\n{err}"
    assert "AWS_ACCOUNT_ID" not in err, f"an account id must not be reported; stderr was:\n{err}"
    assert err.count("AWS_ACCESS_KEY_ID") == 1, (
        f"the placeholder access-key lines must stay quiet; stderr was:\n{err}"
    )


def test_end_to_end_is_clean_without_the_access_key(probe_repo, monkeypatch, capsys, tmp_path):
    """Falsification control: remove the pattern and the same file reports nothing."""
    monkeypatch.chdir(probe_repo)
    original = cec.CRED_VAR_PATTERNS
    cec.CRED_VAR_PATTERNS = PATTERNS_BEFORE_THIS_LEAF
    try:
        assert cec.main() == 1
        err = capsys.readouterr().err
        assert "AWS_ACCESS_KEY_ID" not in err, (
            f"without ACCESS_KEY the line must be out of scope; stderr was:\n{err}"
        )
        assert "AWS_ACCESS_TOKEN" in err, "the already-in-scope line must still report"
    finally:
        cec.CRED_VAR_PATTERNS = original
