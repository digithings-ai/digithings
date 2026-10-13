"""DIG-759: structural non-credentials the length floor reports as credentials.

``CRED_MIN_VALUE_LEN = 12`` with the ``CRED_MIN_ENTROPY_LEN = 17`` waiver admits
any opaque value of 12 or more characters under a credential-named variable, and
that waiver is what makes the band usable at all. Its cost is that it also admits
values that are not credentials under any reading - not because their length or
their entropy is wrong, but because they are a different *kind* of string:

    ``${API_KEY:-}``      a reference the shell resolves at deploy time
    ``user:pass@host``    a connection template
    ``-----BEGIN-----``   a fence promising a key, carrying none

No threshold on a continuous score separates those from ``postgrespass`` - several
of them score *above* the frozen probes - so shape is the only instrument that
works. ``NON_SECRET_VALUE_SHAPES`` in ``scripts/check_example_credentials.py``
adds four classes, plus one predicate, all applied with ``fullmatch``:

  * **interpolation reference** - ``${VAR}``, ``${VAR:-}``, ``$(VAR)``, ``$VAR``,
    ``{{ var }}``, ``<% var %>``;
  * **connection template** - a locator whose no part is as long as a value this
    guard scores, so ``user:pass@host`` is a template and
    ``redis://u:Sup3rS3cretPw2026@cache:6379/0`` is not;
  * **delimiter fence** - a repeated delimiter at both ends, ``-----BEGIN-----``;
  * **placeholder marker plus numeric filler** - ``changeme1234``,
    ``placeholder123``, which ``PLACEHOLDER_PATTERNS`` misses because its
    separator class ``[^A-Za-z0-9]`` rejects the digit run.

``looks_cred_val`` consults them **after** the vendor prefix loop, and
``is_non_secret_shape`` refuses any value carrying whitespace before it looks at
a pattern. Those two facts are the recall argument, and most of this file exists
to hold them: ``test_vendor_prefix_outranks_the_shape_exclusions``,
``test_shape_exclusion_refuses_a_trailing_comment``,
``test_locator_carrying_a_credential_is_still_reported``.

Fifteen of the twenty-one measured false positives are English-word example
passwords (``postgrespass``, ``supersecret123``, ``adminadmin1234``,
``testpassword12``, ``staging-pass-1``, ...) and are deliberately **still
reported**, because the frozen contract requires reporting exactly that shape:
``my_secret_passphrase_2024_ok`` and ``correct-horse-9-Battery-S7`` are 28- and
26-character literal English passphrases that must be reported, and
``Tr0ub4dor&3xyzQ7Lp`` is an 18-character leetspeak English word that must be
reported. Any word-shape or dictionary rule that clears ``supersecret123`` clears
those too, unless it is artificially scoped to the sub-17 band - and a band-scoped
example-password denylist is a list of the measured answers, which trades the
guard's recall (its entire purpose, and the whole point of merged leaf #5044) for
one sample. ``MEASURED_STILL_REPORTED`` pins that trade, and
``test_in_band_frozen_credential_probe_is_still_reported`` pins the two frozen
probes inside the band so the trade cannot be made quietly.

Every probe here is **synthetic**: the shape classes are spelled out literally and
the credential probes are copies of the frozen lists, none taken from git history
and none a real key.

Kept in its own file, alongside the three frozen ones rather than inside them:
``test_check_example_credentials.py``, ``..._short_values.py`` and
``..._vendor_prefixes.py`` are byte-pinned contracts of earlier leaves, and
``..._commented_vendor_prefixes.py`` is DIG-749's red test.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_example_credentials.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_example_credentials_shape_under_test", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cec = _load_module()


@pytest.fixture
def without_shape_exclusions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn ``NON_SECRET_VALUE_SHAPES`` off, leaving the rest of the guard intact.

    Asserting against this instead of re-deriving the guard's own arithmetic in
    the test keeps the two from drifting apart: the subject is exactly
    ``looks_cred_val`` as written, minus the one thing under test.
    """
    monkeypatch.setattr(cec, "is_non_secret_shape", lambda v: False)


# ---------------------------------------------------------------------------
# The four shape classes, one list per class, so a failing parameter id names the
# class rather than a bare string.
# ---------------------------------------------------------------------------
INTERPOLATION_REFERENCES = [
    "${API_KEY:-}",  # the measured false positive
    "${SERVICE_API_KEY}",
    "$(SERVICE_API_KEY)",
    "$SERVICE_API_KEY",
    "${DB_PASSWORD:-}",
    "$(OPENAI_API_KEY)",
]

CONNECTION_TEMPLATES = [
    "user:pass@host",  # the measured false positive - no scheme, so `://` misses it
    "admin:s3cret@db.internal",
    "postgres://app:s3cret@db:5432/app",
    "jdbc:postgresql://u:p@db:5432/app",
    "https://api.x.ai/v1",
    "redis://localhost:6379/0",
    "amqp://guest:guest@rabbit:5672/vhost",
]

FRAMED_ARMOUR = [
    "-----BEGIN-----",  # the measured false positive
    "___WrappedValue9___",
    "***REDACTED***",
]

PLACEHOLDER_MARKER_FILLERS = [
    "changeme1234",  # the measured false positive
    "placeholder123",  # the measured false positive
    "changeme123456789012",  # the digit run is unbounded, so there is no cliff
    "dummy42000042",
    "test12345678",
    "Replace1234567",  # markers are matched case-insensitively, as in is_placeholder
    "CHANGEME00000001",
    "example12345678",
]

SHAPE_CLASSES = {
    "interpolation-reference": INTERPOLATION_REFERENCES,
    "connection-template": CONNECTION_TEMPLATES,
    "delimiter-fence": FRAMED_ARMOUR,
    "placeholder-marker-filler": PLACEHOLDER_MARKER_FILLERS,
}

ALL_SHAPE_PROBES = [v for probes in SHAPE_CLASSES.values() for v in probes]

#: The same four syntaxes as they are written with a space in them - a Helm
#: template, an ERB tag, a PEM header, a banner. Whitespace means "this line is
#: prose", which is a stronger and earlier claim than any shape, so these are
#: deliberately *not* shapes: the exclusion list refuses whitespace before it
#: looks at a pattern, and the inline-comment exclusion would have caught them
#: anyway.
PROSE_WRITTEN_SHAPES = [
    "{{ secrets.API_KEY }}",
    "<% api_key %>",
    "-----BEGIN RSA PRIVATE KEY-----",
    "*** SECRET FOLLOWS ***",
]

#: Every probe above is inside the band, so each fails without this change. A
#: shorter one would be testing the length gate, and this list is the assertion
#: that says so.
SHAPE_PROBES_INSIDE_THE_BAND = [
    v
    for v in ALL_SHAPE_PROBES
    if len(v) >= cec.CRED_MIN_VALUE_LEN
    and cec.shannon_entropy(v) > 0.0
    and not cec.is_placeholder(v)
]

#: A trailing inline comment, as carried by a live ``KEY = ... # comment`` line.
TRAILING_COMMENT = " # rotated 2026-01"

# ---------------------------------------------------------------------------
# Copies of the frozen expected-True probes. The frozen files stay the contract of
# record; these copies exist so this file can assert the one invariant that makes
# the new list safe - none of these values is a shape - without importing a test
# module from another test module.
# ---------------------------------------------------------------------------
FROZEN_TRUE_PROBES = [
    # leaf A: value shapes
    "Qw7Er2Ty5Ui9Op1Astest_Df4Gh6Jk8Lz0Xc2Vb4Nm",
    "Ab3Cd5Ef7Gh9Ij1Kldummy_Lm0No2Pq4Rs6Tu8Vw0Xy2Z",
    "Zy2Xw4Vu6Ts8Rq0Poyour_Qa1Sd3Fg5Hj7Kl9Zn3Xc5Vb7Ms1",
    "Nn8Mm7Ll6Kk5Jj4Iichangeme_Hh2Gg3Ff4Dd5Ss6Rr7Tt8",
    "Bb2Cc4Dd6Ee8Ff0Gg2Hh4Ii6Kk8Ll0Mm2Nn4Pp6Rr8Ss0Tt",
    "Tr0ub4dor&3xyzQ7Lp",
    "aB3&x7Kq9ZmTp2Rw",
    "correct-horse-9-Battery-S7",
    "my_secret_passphrase_2024_ok",
    # leaf B: vendor prefixes, bare and with a comment
    "sk-A1b2C3d4E5f6G7h8I9j0K1l2",
    "sk-proj-A1b2C3d4E5f6G7h8I9j0K1l2",
    "sk-ant-api03-A1b2C3d4E5f6G7h8I9j0K1l2",
    "ghp_proj-9Xk2Lm4Q7rTz1Bv6Nc8Wd0Yh3Js5Ae1Ug",
    "gho_proj-9Xk2Lm4Q7rTz1Bv6Nc8Wd0Yh3Js5Ae1Ug",
    "glpat-proj-9Xk2Lm4Q7rTz1Bv6Nc8Wd0Yh3Js5Ae1Ug",
]

# ---------------------------------------------------------------------------
# The short-value leaf's probes, split by where they sit relative to the band.
# Both in-band ones matter: they are the frozen contract *inside* the range this
# change widens, so a shape rule that cleared them would be a threshold wearing a
# disguise.
# ---------------------------------------------------------------------------
FROZEN_IN_BAND_TRUE_PROBES = [
    "69qm52xx9xb7",  # len 12, H 3.022 - the band's floor
    "5nx2m7mzqm5zqmqq",  # len 16, H 2.750 - the band's ceiling
]

# ---------------------------------------------------------------------------
# The refutation path the brief requires to survive. These score 0.000 bits, so
# they are cleared by "one repeated symbol is evidence against a credential", not
# by anything this change adds. Each is asserted not to be a shape as well as not
# to be reported, so that path cannot quietly be replaced by the new list.
# ---------------------------------------------------------------------------
REPEATED_SYMBOL_FENCES = [
    "aaaaaaaaaaaa",
    "000000000000",
    "xxxxxxxxxxxx",
]

# ---------------------------------------------------------------------------
# The measured block from DIG-759, value by value, so the claim in the module
# docstring can be checked instead of believed. Six of the twenty-one stop being
# reported; fifteen are written arguments, not oversights.
# ---------------------------------------------------------------------------
MEASURED_EXCLUDED_BY_SHAPE = [
    "changeme1234",
    "placeholder123",
    "${API_KEY:-}",
    "user:pass@host",
    "-----BEGIN-----",
]

MEASURED_ALREADY_UNDER_THE_FLOOR = [
    "pgadmin123",  # ten characters - below CRED_MIN_VALUE_LEN before this change
]

MEASURED_STILL_REPORTED = [
    "postgrespass",
    "mysecretvalue",
    "digichat12345",
    "qwertyuiop123",
    "hunter2hunter",
    "notasecret12",
    "rootpassw0rd",
    "supersecret123",
    "my-secret-pass",
    "devpassword12",
    "defaultpass12",
    "localdevpass1",
    "adminadmin1234",
    "testpassword12",
    "staging-pass-1",
]

MEASURED_BLOCK = (
    MEASURED_EXCLUDED_BY_SHAPE + MEASURED_ALREADY_UNDER_THE_FLOOR + MEASURED_STILL_REPORTED
)

# ---------------------------------------------------------------------------
# Values that look like a shape but are not, and must keep being reported. Each is
# a false negative this list would create if it were written one character wider.
# ---------------------------------------------------------------------------
NEAR_MISS_TRUE_PROBES = [
    # A non-empty default puts a literal under a credential name, which is exactly
    # what the guard exists to report - so `${...}` stops at the empty default.
    "${API_KEY:-s3cret}",
    "${API_KEY:-x}",
    # Operators no engine emits, so they cannot be an empty expansion.
    "${API_KEY:-=}",
    # An `@` before the `:` is not userinfo, so this stays a password.
    "P@ss:word1234",
    "P@ssw0rd:1234567",
]

#: A locator is only a connection template when nothing in it is as long as a
#: value this guard scores. Each of these puts a credential in one of the three
#: places a locator can hide one, and each was a recall hole when the class was a
#: bare ``scheme://`` regex.
LOCATOR_CARRYING_A_CREDENTIAL = [
    # userinfo
    "redis://default:Sup3rS3cretPw2026@cache.internal:6379/0",
    "jdbc:postgresql://app:Xk8pQ2vN6zLw2026@db.prod:5432/app",
    "https://admin:Q7xR2vN9mK4pL6tB@crm.force.com",
    # a query parameter
    "https://api.x.ai/v1/chat/completions?api_key=sk-proj-AbCdEf123456GhIjKlMnOpQr",
    # userinfo in a git remote
    "git+https://ghs_16C7e42F292c6912E7710c838347Ae178B4a@github.com/acme/app.git",
    # the path
    "https://hooks.slack.com/services/T00000/B11111/abcDEF123456ghiJKL789",
]


@pytest.mark.parametrize("value", INTERPOLATION_REFERENCES)
def test_interpolation_reference_is_not_a_credential(value: str) -> None:
    """A reference resolved at deploy time is not the secret it points at."""
    assert cec.is_non_secret_shape(value) is True
    assert cec.looks_cred_val(value) is False


@pytest.mark.parametrize("value", CONNECTION_TEMPLATES)
def test_connection_template_is_not_a_credential(value: str) -> None:
    """A DSN says where to connect, not how to authenticate."""
    assert cec.is_non_secret_shape(value) is True
    assert cec.looks_cred_val(value) is False


@pytest.mark.parametrize("value", FRAMED_ARMOUR)
def test_delimiter_fence_is_not_a_credential(value: str) -> None:
    """Framing around a key is not a key."""
    assert cec.is_non_secret_shape(value) is True
    assert cec.looks_cred_val(value) is False


@pytest.mark.parametrize("value", PLACEHOLDER_MARKER_FILLERS)
def test_placeholder_marker_with_numeric_filler_is_not_a_credential(value: str) -> None:
    """``PLACEHOLDER_PATTERNS`` names the marker; the digit run defeats its separator."""
    assert cec.is_non_secret_shape(value) is True
    assert cec.looks_cred_val(value) is False


@pytest.mark.parametrize("value", SHAPE_PROBES_INSIDE_THE_BAND)
def test_shape_probe_is_reported_without_the_exclusion_list(
    value: str, without_shape_exclusions: None
) -> None:
    """The exclusion list is doing the work, not a threshold that moved.

    The guard with the list switched off reports every one of these, so each test
    above fails without this change and no other instrument can be quietly
    substituted for it.
    """
    assert cec.looks_cred_val(value) is True


def test_every_shape_probe_is_inside_the_band() -> None:
    """The list above is the class lists, so no probe can pass by being too short.

    A probe under ``CRED_MIN_VALUE_LEN`` would test the length gate instead of the
    exclusion list, which is how a shape class can look covered while testing
    nothing.
    """
    assert sorted(SHAPE_PROBES_INSIDE_THE_BAND) == sorted(ALL_SHAPE_PROBES)


@pytest.mark.parametrize("value", PROSE_WRITTEN_SHAPES)
def test_shape_written_with_spaces_is_prose(value: str) -> None:
    """A shape written with whitespace in it is a comment, and comments are not scored.

    These four are the syntaxes the classes above cover, as they actually appear in
    a file. They are not excluded because they are shapes - they are excluded
    because whitespace means the line is prose, which the guard decided before any
    shape was consulted.
    """
    assert cec.is_non_secret_shape(value) is False
    assert cec.looks_cred_val(value) is False


@pytest.mark.parametrize("value", ALL_SHAPE_PROBES)
def test_shape_exclusion_refuses_a_trailing_comment(value: str) -> None:
    """Nothing after the value can be swallowed - the invariant that protects the prefix loop.

    A value carrying an inline ``# comment`` never reaches the entropy score, so the
    vendor prefix loop is the only gate that can catch it. If any pattern here
    matched a shape probe plus a trailing comment, this change would introduce the
    exact defect DIG-50 leaf B fixed, and would break DIG-749's red test when it
    lands. Asserted against ``is_non_secret_shape`` rather than ``looks_cred_val``
    so the guarantee is the shape list's own, not a side effect of ordering.

    Only the trailing direction is claimed. A *prefix* does not always break a shape
    - ``xuser:pass@host`` is still userinfo before a host - and that is correct: the
    list decides what kind of string this is, not whether something precedes it.
    """
    assert cec.is_non_secret_shape(value + TRAILING_COMMENT) is False


@pytest.mark.parametrize("value", FROZEN_TRUE_PROBES)
def test_no_frozen_credential_probe_is_a_non_secret_shape(value: str) -> None:
    """None of the frozen expected-True values may match the new list.

    The strong form of the no-regression claim: it holds on the pattern list
    itself, so it survives any reordering of ``looks_cred_val`` later.
    """
    assert cec.is_non_secret_shape(value) is False
    assert cec.looks_cred_val(value) is True


@pytest.mark.parametrize("value", FROZEN_IN_BAND_TRUE_PROBES)
def test_in_band_frozen_credential_probe_is_still_reported(value: str) -> None:
    """The 12-to-16 band the shape classes were added for keeps reporting credentials.

    ``5nx2m7mzqm5zqmqq`` scores 2.750, below several of the false positives this
    change clears. No entropy threshold can hold both, so this test is the reason
    the threshold was not the instrument.
    """
    assert cec.is_non_secret_shape(value) is False
    assert cec.looks_cred_val(value) is True


@pytest.mark.parametrize("value", NEAR_MISS_TRUE_PROBES)
def test_near_miss_value_is_still_reported(value: str) -> None:
    """A shape written one character wider must not become a false negative."""
    assert cec.is_non_secret_shape(value) is False
    assert cec.looks_cred_val(value) is True


@pytest.mark.parametrize("value", LOCATOR_CARRYING_A_CREDENTIAL)
def test_locator_carrying_a_credential_is_still_reported(value: str) -> None:
    """Being a URL is not a defence; carrying a credential in one still reports.

    Every value here is a locator, and every one of them holds a secret in the one
    place its kind has: userinfo, a query parameter, a token in the path. A
    connection template is a locator with nothing in it worth reporting, so the
    class asks that question per part rather than waving at the scheme.
    """
    assert cec.looks_cred_val(value) is True


@pytest.mark.parametrize("value", ALL_SHAPE_PROBES)
def test_vendor_prefix_outranks_the_shape_exclusions(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordering is the recall argument, so it is pinned directly.

    A vendor prefix is the strongest signal this guard has, and the shape classes
    run after that loop precisely so nothing here can outrank it. Read from the
    source the ordering is a claim; this makes it executable by teaching the
    prefix loop to match a shape probe and checking the value still reports.
    """
    monkeypatch.setattr(cec, "CRED_VALUE_PATTERNS", [re.escape(value[:2]) + ".*"])
    assert cec.looks_cred_val(value) is True


@pytest.mark.parametrize("value", REPEATED_SYMBOL_FENCES)
def test_repeated_symbol_refutation_path_survives(value: str) -> None:
    """A repeated symbol stays refuted by entropy, not by the new shape list."""
    assert cec.is_non_secret_shape(value) is False
    assert cec.shannon_entropy(value) == 0.0
    assert cec.looks_cred_val(value) is False


@pytest.mark.parametrize("value", MEASURED_EXCLUDED_BY_SHAPE)
def test_measured_false_positive_is_excluded(value: str) -> None:
    """The five measured false positives the shape classes are there to clear."""
    assert cec.is_non_secret_shape(value) is True
    assert cec.looks_cred_val(value) is False


@pytest.mark.parametrize("value", MEASURED_ALREADY_UNDER_THE_FLOOR)
def test_measured_false_positive_was_already_under_the_floor(value: str) -> None:
    """The twenty-first measured value never reached the floor; say so rather than claim it."""
    assert len(value) < cec.CRED_MIN_VALUE_LEN
    assert cec.is_non_secret_shape(value) is False
    assert cec.looks_cred_val(value) is False


@pytest.mark.parametrize("value", MEASURED_STILL_REPORTED)
def test_measured_example_password_is_deliberately_reported(value: str) -> None:
    """Fifteen measured false positives stay reported, with the argument on the record.

    The guard exists to catch a weak password in an example file, and
    ``my_secret_passphrase_2024_ok`` and ``correct-horse-9-Battery-S7`` are frozen
    expected-True probes. Any rule that clears these clears those, so these are
    reported on purpose rather than missed.
    """
    assert cec.is_non_secret_shape(value) is False
    assert cec.looks_cred_val(value) is True


# ---------------------------------------------------------------------------
# The conflict, stated as data so that it is checked rather than argued.
#
# ``postgrespass`` and ``testpassword12`` are the reported cases that motivate a
# second instrument: a weak-word list, the way gitleaks and trufflehog work. It is
# not available here, and the reason is not that a list would be unprincipled. It
# is that every stem such a list needs is already inside a frozen probe:
# ``secret`` and ``passphrase`` in ``my_secret_passphrase_2024_ok``, ``correct``
# and ``horse`` in ``correct-horse-9-Battery-S7``. Both are the two most
# example-looking strings in the whole frozen set - the second is the canonical
# "not a real passphrase" example by construction. A weak-word rule that reports
# ``supersecret123`` has to report them, and they are pinned to True.
#
# So the choice this leaf makes is not "shape, or a lexicon". It is: shape for the
# values that have a shape, and a kept false positive for the values that are
# indistinguishable from the contract. Each entry below is the stem, the frozen
# probe holding it, and nothing else.
# ---------------------------------------------------------------------------
WEAK_STEMS_HELD_BY_A_FROZEN_PROBE = {
    "secret": "my_secret_passphrase_2024_ok",
    "passphrase": "my_secret_passphrase_2024_ok",
    "correct": "correct-horse-9-Battery-S7",
    "horse": "correct-horse-9-Battery-S7",
    "test": "Qw7Er2Ty5Ui9Op1Astest_Df4Gh6Jk8Lz0Xc2Vb4Nm",
    "dummy": "Ab3Cd5Ef7Gh9Ij1Kldummy_Lm0No2Pq4Rs6Tu8Vw0Xy2Z",
    "changeme": "Nn8Mm7Ll6Kk5Jj4Iichangeme_Hh2Gg3Ff4Dd5Ss6Rr7Tt8",
    "your": "Zy2Xw4Vu6Ts8Rq0Poyour_Qa1Sd3Fg5Hj7Kl9Zn3Xc5Vb7Ms1",
}


@pytest.mark.parametrize("stem,probe", sorted(WEAK_STEMS_HELD_BY_A_FROZEN_PROBE.items()))
def test_weak_stem_the_measured_block_would_need_is_held_by_a_frozen_probe(
    stem: str, probe: str
) -> None:
    """Every stem a weak-word rule would need is already a frozen expected-True probe.

    This is the mechanical form of the argument on ``MEASURED_STILL_REPORTED``.
    If a frozen probe were ever changed so that the measured block became clearable,
    this test is the place that says so, rather than a future leaf rediscovering the
    conflict by widening the lexicon and wondering which probe broke.
    """
    frozen = FROZEN_TRUE_PROBES + FROZEN_IN_BAND_TRUE_PROBES
    assert probe in frozen, f"{probe} is no longer a frozen expected-True probe"
    assert re.search(stem, probe, re.I), f"{stem} does not occur in {probe}"


def test_measured_block_is_the_whole_list() -> None:
    """Twenty-one values, accounted for: five excluded, one under the floor, fifteen reported."""
    assert len(MEASURED_BLOCK) == 21
    assert len(set(MEASURED_BLOCK)) == 21


@pytest.mark.parametrize("run", [3, 20, 39])
def test_delimiter_fence_within_the_bound_is_framing(run: int) -> None:
    """A fence of at most 80 characters is framing, and the interior carries the payload."""
    assert cec.is_non_secret_shape("-" * run + "K" + "-" * run) is True


@pytest.mark.parametrize("run", [40, 100, 1000])
def test_delimiter_run_past_the_bound_is_data(run: int) -> None:
    """Past 80 characters, a fence is data wearing fence characters.

    Also the reason the bound is there: unbounded, this pattern cost four times as
    long per doubling of the input, and ``is_non_secret_shape`` runs on every line
    of every example file in the tree.
    """
    assert len("-" * run + "K" + "-" * run) > 80
    assert cec.is_non_secret_shape("-" * run + "K" + "-" * run) is False


def test_bare_delimiter_run_is_a_shape() -> None:
    """A value of nothing but punctuation is not a credential at any length it admits."""
    assert cec.is_non_secret_shape("----------") is True


def test_guard_reports_a_leak_in_a_synthetic_example_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The negative control ``main() == 0`` cannot give.

    A guard that reported nothing at all passes ``main() == 0``, so the corpus
    test below proves nothing on its own. This runs ``main`` against a synthetic
    tracked ``.env.example`` holding a leak a locator shape must not swallow.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".env.example").write_text(
        "\n".join(
            [
                "# comment",
                "DATABASE_URL=postgres://app:s3cret@localhost:5432/app",
                "REDIS_PASSWORD=redis://default:Sup3rS3cretPw2026@cache.internal:6379/0",
                "API_KEY=9z63367327xqzbz426",
                "",
            ]
        )
    )
    subprocess.run(["git", "add", ".env.example"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    assert cec.main() == 1
    findings = capsys.readouterr().err
    assert "REDIS_PASSWORD" in findings
    # The template next to it is not a finding, and the leak is the only one.
    assert "DATABASE_URL" not in findings


def test_tracked_example_files_stay_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real regression gate: the guard must still exit 0 on the tracked files."""
    monkeypatch.chdir(REPO_ROOT)
    assert cec.main() == 0
