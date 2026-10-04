"""Regression tests for vendor-prefixed values in scripts/check_example_credentials.py.

DIG-50 leaf B, follow-up: after the value-shape test moved to a character
distribution score, the ``sk-`` entry of ``CRED_VALUE_PATTERNS`` kept its ``$``
anchor (``^sk-[A-Za-z0-9]{20,}$``) while ``^ghp_``, ``^gho_`` and ``^glpat-`` are
prefix-only. A prefixed key carrying a trailing inline comment therefore matched
three of the four vendor prefixes and was reported clean for the fourth - the
highest-value one. Green CI and the tracked-corpus fence both stayed green over it.

The contract pinned here: a vendor prefix is matched on the value's *leading*
token, so nothing after the key may hide it, and any body class must be the
alphabet the vendor really uses. Both halves matter because a value carrying a
comment never reaches the entropy score - ``looks_cred_val`` rejects prose first -
so the vendor loop is the only gate that can catch a commented key.

  * a prefixed key followed by a ``# comment`` is a credential, for every prefix
    and every realistic body shape the guard knows;
  * the two real ``sk-`` families, ``sk-proj-`` and ``sk-ant-api03-``, put a
    ``-`` inside the first 20 characters and must survive that;
  * widening the body class must not drop ``sk-``'s minimum key length.

Kept in its own file rather than added to
``test_check_example_credentials.py``, which is the pinned contract for this leaf
and must stay byte-identical to its committed form.
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
    spec = importlib.util.spec_from_file_location("check_example_credentials_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cec = _load_module()

#: 24 characters of key body, comfortably past ``sk-``'s {20,} minimum.
ALNUM_BODY = "A1b2C3d4E5f6G7h8I9j0K1l2"

#: A hyphen inside the first 20 characters, which is where OpenAI's ``sk-proj-``
#: and Anthropic's ``sk-ant-api03-`` families put theirs.
URLSAFE_BODY = "proj-9Xk2Lm4Q7rTz1Bv6Nc8Wd0Yh3Js5Ae1Ug"

#: Every vendor prefix in ``CRED_VALUE_PATTERNS``.
VENDOR_PREFIXES = ["sk-", "ghp_", "gho_", "glpat-"]

#: Real-world key shapes, one per prefix. The prefixes that carry their own body
#: requirement get the body that satisfies it; the bare prefixes get the
#: URL-safe body, which every one of them also accepts.
REAL_KEY_SHAPES = [
    "sk-" + ALNUM_BODY,  # legacy OpenAI-style
    "sk-proj-" + ALNUM_BODY,  # OpenAI project key
    "sk-ant-api03-" + ALNUM_BODY,  # Anthropic key
    "ghp_" + URLSAFE_BODY,  # GitHub personal access token
    "gho_" + URLSAFE_BODY,  # GitHub OAuth token
    "glpat-" + URLSAFE_BODY,  # GitLab personal access token
]

#: A trailing inline comment, as carried by a live ``KEY = ... # comment`` line.
TRAILING_COMMENT = " # rotated 2026-01"


@pytest.mark.parametrize("key", REAL_KEY_SHAPES)
def test_vendor_prefixed_key_with_trailing_comment_is_a_credential(key: str) -> None:
    """A comment after the key must not hide a prefixed credential."""
    assert cec.looks_cred_val(key + TRAILING_COMMENT) is True


@pytest.mark.parametrize("key", REAL_KEY_SHAPES)
def test_vendor_prefixed_key_without_comment_is_a_credential(key: str) -> None:
    """Control for the case above: the bare key was already caught."""
    assert cec.looks_cred_val(key) is True


def test_every_prefix_agrees_on_every_key_shape() -> None:
    """The defect was one prefix behaving differently from the other three.

    Asserted differentially rather than per-shape, so that a prefix added later
    cannot quietly reintroduce a stricter body rule.
    """
    bodies = [ALNUM_BODY, URLSAFE_BODY]
    for suffix in ("", TRAILING_COMMENT, " # see the runbook"):
        for body in bodies:
            verdicts = {
                prefix: cec.looks_cred_val(prefix + body + suffix) for prefix in VENDOR_PREFIXES
            }
            assert len(set(verdicts.values())) == 1, (
                f"prefixes disagree on {body!r}{suffix!r}: {verdicts}"
            )
            # Agreement alone is satisfied by every prefix going dead, which is a
            # mutation that must fail rather than pass.
            assert next(iter(set(verdicts.values()))) is True, (
                f"every prefix agrees that {body!r}{suffix!r} reads clean: {verdicts}"
            )


def test_no_vendor_pattern_is_end_anchored() -> None:
    """A structural guard on the same defect class.

    An end anchor - ``$`` or its ``\\Z`` spelling - is what let a trailing comment
    hide a prefixed key. This catches the literal spellings; it is a backstop
    behind the behavioural tests above, not a substitute for them, which is why
    its name claims only what it checks.
    """
    end_anchored = [p for p in cec.CRED_VALUE_PATTERNS if p.endswith(("$", r"\Z"))]
    assert end_anchored == [], f"end-anchored vendor pattern(s): {end_anchored}"


def test_sk_prefix_keeps_its_minimum_key_length() -> None:
    """Widening the body class must not turn ``sk-`` into a prefix-only pattern.

    Checked against the pattern list rather than ``looks_cred_val``: a short
    ``sk-`` key still scores high enough to be reported, so the public function
    cannot tell which of its two gates caught it.
    """
    matching = [p for p in cec.CRED_VALUE_PATTERNS if re.match(p, "sk-" + ALNUM_BODY[:19])]
    assert matching == [], f"sk- matched a 19-character key body via {matching}"
    matching = [p for p in cec.CRED_VALUE_PATTERNS if re.match(p, "sk-" + ALNUM_BODY)]
    assert matching, "sk- no longer matches a 24-character key body"
