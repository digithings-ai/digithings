"""Regression tests for vendor-prefixed values in scripts/check_example_credentials.py.

DIG-50 leaf B, follow-up: after the value-shape test moved to a character
distribution score, the ``sk-`` entry of ``CRED_VALUE_PATTERNS`` kept its ``$``
anchor (``^sk-[A-Za-z0-9]{20,}$``) while ``^ghp_``, ``^gho_`` and ``^glpat-`` are
prefix-only. A prefixed key carrying a trailing inline comment therefore matched
three of the four vendor prefixes and was reported clean for the fourth - the
highest-value one. Green CI and the 13-file fence both stayed green over it.

The contract pinned here: a vendor prefix is matched on the value's *leading*
token, so nothing after the key may hide it.

  * a prefixed key followed by a ``# comment`` is still a credential, for every
    prefix the guard knows;
  * dropping the anchor must not drop ``sk-``'s minimum key length.

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
    spec = importlib.util.spec_from_file_location(
        "check_example_credentials_under_test", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cec = _load_module()

#: 24 characters of key body, comfortably past ``sk-``'s {20,} minimum.
KEY_BODY = "A1b2C3d4E5f6G7h8I9j0K1l2"

#: Every vendor prefix in ``CRED_VALUE_PATTERNS``.
VENDOR_PREFIXES = ["sk-", "ghp_", "gho_", "glpat-"]

#: A trailing inline comment, as carried by a live ``KEY = ... # comment`` line.
TRAILING_COMMENT = " # rotated 2026-01"


@pytest.mark.parametrize("prefix", VENDOR_PREFIXES)
def test_vendor_prefixed_key_with_trailing_comment_is_a_credential(prefix: str) -> None:
    """A comment after the key must not hide a prefixed credential."""
    assert cec.looks_cred_val(prefix + KEY_BODY + TRAILING_COMMENT) is True


@pytest.mark.parametrize("prefix", VENDOR_PREFIXES)
def test_vendor_prefixed_key_without_comment_is_a_credential(prefix: str) -> None:
    """Control for the case above: the bare key was already caught."""
    assert cec.looks_cred_val(prefix + KEY_BODY) is True


def test_no_vendor_pattern_is_end_anchored() -> None:
    """The defect itself: ``$`` let a trailing comment hide a prefixed key.

    ``^ghp_``, ``^gho_`` and ``^glpat-`` are prefix-only and survive a trailing
    comment. ``^sk-[A-Za-z0-9]{20,}$`` did not, which made ``sk-`` - the
    highest-value prefix - the one a comment could hide. Asserted over the whole
    list so the next prefix added cannot reintroduce it.
    """
    end_anchored = [p for p in cec.CRED_VALUE_PATTERNS if p.endswith("$")]
    assert end_anchored == [], f"end-anchored vendor pattern(s): {end_anchored}"


def test_sk_prefix_keeps_its_minimum_key_length() -> None:
    """Un-anchoring ``sk-`` must not turn it into a prefix-only pattern.

    Checked against the pattern list rather than ``looks_cred_val``: a short
    ``sk-`` key still scores high enough to be reported, so the public function
    cannot tell which of its two gates caught it.
    """
    short = [p for p in cec.CRED_VALUE_PATTERNS if re.match(p, "sk-" + KEY_BODY[:19])]
    assert short == [], f"sk- matched a 19-character key body via {short}"
    long = [p for p in cec.CRED_VALUE_PATTERNS if re.match(p, "sk-" + KEY_BODY)]
    assert long, "sk- no longer matches a 24-character key body"