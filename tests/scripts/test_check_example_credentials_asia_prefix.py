"""DIG-42 leaf B follow-up: the `ASIA` prefix is in `CRED_VALUE_PATTERNS` and nothing tests it.

[DIG-749](/DIG/issues/DIG-749) asked the board whether `CRED_VALUE_PATTERNS`
should keep a 7th vendor prefix, `ASIA` (the AWS STS temporary-credential
access key ID). The board answered twice to keep it (card `9db4681d`, accepted
2026-10-05) and PR #5130 merged the `r'^ASIA[A-Za-z0-9]{16,}'` line as
`9e6a0963e` on 2026-10-06.

The line is shipped. Before this file, nothing tested it. Deleting the `ASIA`
line in a scratch worktree at the merge commit left all 81 credential tests
green and `scripts/check_example_credentials.py` still printing `OK` at exit 0,
so the suite could not see the prefix go. That is the exact defect class the
prefix list exists to close - a prefix the guard has never heard of reports
clean behind a comment while the identical key is reported bare - and a
board-approved behaviour that no test pins will be refactored away by someone
who does not know it was deliberate.

Why the *commented* form is the probe, and not the bare one. `looks_cred_val`
rejects prose before it takes any score:

    if v.startswith('#') or any(c.isspace() for c in v):
        return False

so a value written as `AWS_TEMP_KEY = ASIA...  # from IAM role` carries
whitespace and is dropped before `shannon_entropy()` ever runs. On that path
the vendor-prefix loop is the *only* gate left. The bare value is reported in
both states - the entropy score catches it without help from the prefix - so a
bare-only probe would pass on the mutant and pin nothing. Measured through
`looks_cred_val` with the body below:

    guard state                        bare    + "  # from IAM role"
    ---------------------------------  ------  --------------------
    merge commit 9e6a0963e (line kept)    True   True
    mutant         (line deleted)        True   False   <-- only red cell

The commented case is therefore a real behavioural pin: it is red when the
`ASIA` line is gone and green while it is there.

`AKIA`, the sibling AWS prefix, is already covered by the frozen
`test_check_example_credentials_commented_vendor_prefixes.py` via its `aws_akia`
entry. `ASIA` is not in that file's list - the board's decision landed after it
was frozen - so nothing carried the coverage across, and that is the gap this
file fills. It is kept in its own file, per the same convention, so it cannot
conflict with the three pinned contracts this guard already owns.

Every value below is **synthetic**: `EXAMPLE` is not hex and the body is
deliberately made of consonant/digit letters so it carries no real key. The
comment text is the shape a developer writes in `.env.example`, where the guard
is actually pointed at real credentials.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_example_credentials.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_example_credentials_asia_prefix_under_test", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cec = _load_module()

#: An AWS STS temporary access key ID. `ASIA` is 4 characters and a real access
#: key ID is 20 in *total*, so the body is 16 - a floor of 20 on the body would
#: miss every real key, which is why the pattern says `{16,}`.
ASIA_KEY = "ASIAIOSFODNN7EXAMPLE"

#: The trailing inline comment in the shape the tracked example files use, with
#: the two spaces that separate it from the key in `.env.example`. `main()` also
#: leaves a leading space after the `=`, which `looks_cred_val` strips, so the
#: padding around the key is not what this probe is about - the `#` is.
COMMENT = "  # from IAM role"

#: Both forms the guard must report, each with the id pytest will print.
FORMS = [
    ("bare", ASIA_KEY),
    ("commented", ASIA_KEY + COMMENT),
]


def test_asia_is_a_known_credential_value_pattern():
    """The prefix list carries an `ASIA` entry; this pins its presence, not just its effect."""
    asia = [p for p in cec.CRED_VALUE_PATTERNS if p.startswith("^ASIA")]
    assert asia, (
        "CRED_VALUE_PATTERNS holds no `^ASIA` entry. The board approved keeping it "
        "(DIG-749, card `9db4681d`) and PR #5130 shipped it. Remove it only with "
        "that decision reversed - the behavioural probes below go red with it."
    )


@pytest.mark.parametrize(("value",), [(v,) for _, v in FORMS], ids=[i for i, _ in FORMS])
def test_asia_temporary_key_is_in_scope(value):
    """A bare `ASIA` key is reported today and stays reported."""
    assert cec.looks_cred_val(value) is True, (
        f"looks_cred_val({value!r}) is False, but this probe is a vendor key the "
        "guard already reports bare. If this one is red too, the length or entropy "
        "floor moved - that is a different defect from the commented case below."
    )


def test_asia_temporary_key_behind_a_comment_is_in_scope():
    """The pin that matters: the comment must not hide the key, and only the prefix loop can catch it.

    This is the assertion that fails on a guard with the `ASIA` line deleted and
    passes while the line is present, so it is what makes the file non-vacuous.
    """
    commented = ASIA_KEY + COMMENT
    assert cec.looks_cred_val(commented) is True, (
        f"looks_cred_val({commented!r}) is False. The value carries a trailing "
        f"`# comment`, so the prose exclusion drops it before the entropy score "
        f"runs and `CRED_VALUE_PATTERNS` is the only gate left. The bare form "
        f"{ASIA_KEY!r} is reported, so nothing about the key itself hides it - "
        "only the comment does. Either the `ASIA` line is gone from the guard or "
        "its body class stopped matching a real STS key."
    )


def test_prose_fence_stays_clean():
    """The fence: widening the prefix list must not turn a comment into a credential."""
    for prose in ("", "   # rotate this key quarterly", "# from IAM role"):
        assert cec.looks_cred_val(prose) is False, (
            f"looks_cred_val({prose!r}) is True. This is prose, not a key. A "
            "pattern loose enough to flag it blocks every future pull request."
        )
