"""DIG-4809 item 5: the `ghs_<appid>_<jwt>` token format is accepted, and a real one is caught.

The digithings App plan (DIG-4803) issues four GitHub Apps, and the tokens
those apps mint are installation tokens. GitHub writes those as `ghs_` plus an
opaque body; the plan writes the shape down as `ghs_<appid>_<jwt>` - the
numeric app id, an underscore, then the token body.

Two things have to hold at once, and they pull in opposite directions:

* the **documented placeholder** `ghs_<appid>_<jwt>` is the form the docs and
  the example files use. It is a placeholder, and the guard has to accept it -
  a guard that reports the documented form blocks every pull request that
  writes an example file down.
* a **real** token of that shape is a credential and has to be reported, in
  every place the guard looks: bare, and behind a trailing `# comment`, which
  is the shape `.env.example` carries and the one the vendor-prefix loop
  exists for.

A bare `ghs_` prefix rule cannot tell the two apart - it would report the
placeholder as a credential - so the rule is anchored on the app id, and the
placeholder is recognised by the angle bracket a real base64url token can
never hold.

Every value below is **synthetic**: the app id is a plain number and the token
body is assembled from parts, so no real token is written down here, and the
file holds no contiguous token-shaped literal.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_example_credentials.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_example_credentials_github_app_token_under_test", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cec = _load_module()

#: The numeric app id the token is minted for.
APP_ID = "123456"

#: A token body in the shape a JWT takes: three base64url segments joined by
#: dots. Built in parts so the file holds no contiguous token-shaped literal.
JWT_HEAD = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
JWT_BODY = "eyJpc3MiOiIxMjM0NTY3ODkwIn0."
JWT_SIGN = "SflKxwRJSMeKKF2QT4" + "fwpMeJf36POk6yJV_adQssw5c"

#: The app token of DIG-4803: prefix, app id, separator, body.
APP_TOKEN = "ghs_" + APP_ID + "_" + JWT_HEAD + JWT_BODY + JWT_SIGN

#: The plain installation token GitHub issues: the prefix and an opaque body,
#: with no app id and no separator.
PLAIN_TOKEN = "ghs_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

#: The placeholder the docs and the example files use.
PLACEHOLDER = "ghs_<appid>_<jwt>"

#: A trailing inline comment, in the shape the tracked example files carry.
COMMENT = "  # minted by the ci app"


def test_app_token_is_a_credential() -> None:
    assert cec.looks_cred_val(APP_TOKEN) is True


def test_app_token_behind_a_comment_is_a_credential() -> None:
    """The comment must not hide it.

    A value carrying whitespace is rejected before the entropy score runs, so
    the vendor-prefix loop is the only gate that can catch it. That loop is
    the reason the app-token rule is in `CRED_VALUE_PATTERNS` at all.
    """
    assert cec.looks_cred_val(APP_TOKEN + COMMENT) is True


def test_plain_installation_token_is_a_credential() -> None:
    assert cec.looks_cred_val(PLAIN_TOKEN) is True
    assert cec.looks_cred_val(PLAIN_TOKEN + COMMENT) is True


def test_the_documented_placeholder_is_not_a_credential() -> None:
    """`ghs_<appid>_<jwt>` is the form the docs use; it must stay accepted."""
    assert cec.looks_cred_val(PLACEHOLDER) is False


def test_the_documented_placeholder_is_not_a_credential_under_a_credential_name() -> None:
    """The name the placeholder is written under must not change the verdict."""
    assert cec.looks_cred_var("GITHUB_APP_TOKEN") is True
    assert cec.looks_cred_val(PLACEHOLDER, "GITHUB_APP_TOKEN") is False


def test_a_placeholder_word_does_not_hide_an_app_token() -> None:
    """The exemption needs the angle bracket.

    A real token is base64url, so it cannot hold one. A value that only looks
    like the placeholder - a placeholder *word* rather than a placeholder
    bracket - is a credential.
    """
    assert cec.looks_cred_val("ghs_" + APP_ID + "_your_token_here_000000") is True


def test_the_app_token_rules_are_not_end_anchored() -> None:
    """A structural guard on the same defect class as the vendor prefixes.

    An end anchor is what lets a trailing comment hide a prefixed key.
    """
    rules = [p for p in cec.CRED_VALUE_PATTERNS if p.startswith("^ghs_")]
    assert rules, "CRED_VALUE_PATTERNS holds no `^ghs_` entry"
    end_anchored = [p for p in rules if p.endswith(("$", r"\Z"))]
    assert end_anchored == [], f"end-anchored app-token pattern(s): {end_anchored}"


def test_the_app_token_rule_matches_the_app_token_and_not_the_placeholder() -> None:
    """The rule is anchored on the app id, which is what tells the two apart."""
    rules = [p for p in cec.CRED_VALUE_PATTERNS if p.startswith("^ghs_")]
    assert any(re.match(p, APP_TOKEN) for p in rules), rules
    assert not any(re.match(p, PLACEHOLDER) for p in rules), rules


def test_the_tracked_example_files_stay_clean() -> None:
    """The corpus fence: no tracked `.example` / `.template` file is reported."""
    import os

    cwd = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        assert cec.main() == 0
    finally:
        os.chdir(cwd)
