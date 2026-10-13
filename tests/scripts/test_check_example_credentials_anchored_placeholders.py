"""Regression tests for placeholder matching in scripts/check_example_credentials.py.

DIG-50 defect 1: ``PLACEHOLDER_PATTERNS`` were matched with an unanchored
``re.search``, so ``your_``, ``example_``, ``test_``, ``dummy_``, ``placeholder``,
``changeme`` and ``<...>`` matched *anywhere* inside a value, case-insensitively. Only
two entries were anchored (``^(replace|REPLACE|CHANGE_ME|TODO|FIXME|CHANGEME)`` and
``^$``). A real credential long enough to satisfy the value-shape patterns was therefore
classified as a placeholder and waved through whenever it happened to contain one of
those words in the middle.

These tests pin the anchored contract:

* a placeholder word *after* the first token must not hide a credential;
* a placeholder word *as* the first token (separator-tolerant) stays a placeholder;
* the guard still reports nothing on the tracked ``.example`` / ``.template`` files.
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
        "check_example_credentials_under_test", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cec = _load_module()

#: Values that satisfy the value-shape patterns (``[A-Za-z0-9_.-]{32,}``) and embed a
#: placeholder word after the first token. Each must be reported as a credential.
#: The last entry is a positive control with no placeholder word at all.
MID_WORD_SECRETS = [
    "Qw7Er2Ty5Ui9Op1Astest_Df4Gh6Jk8Lz0Xc2Vb4Nm",
    "Ab3Cd5Ef7Gh9Ij1Kldummy_Lm0No2Pq4Rs6Tu8Vw0Xy2Z",
    "Zy2Xw4Vu6Ts8Rq0Poyour_Qa1Sd3Fg5Hj7Kl9Zn3Xc5Vb7Ms1",
    "Nn8Mm7Ll6Kk5Jj4Iichangeme_Hh2Gg3Ff4Dd5Ss6Rr7Tt8",
    "Bb2Cc4Dd6Ee8Ff0Gg2Hh4Ii6Kk8Ll0Mm2Nn4Pp6Rr8Ss0Tt",
]

#: Values whose *first* token is a placeholder word, or which are wholly a placeholder
#: form. These must stay placeholders after anchoring. ``your-litellm-key-here`` is live
#: in ``docs/templates/project/.env.example`` and ``replace-with-...`` values are live in
#: ``.env.example`` and ``infra/digichat-release/*.example`` today.
LEADING_PLACEHOLDERS = [
    "replace-with-openssl-rand-base64-32",
    "replace-with-strong-password",
    "replace-with-your-fred-api-key",
    "your-litellm-key-here",
    "your_openai_key_here",
    "CHANGE_ME-abc123def456ghi789jkl",
    "<your-api-key-here>",
    "TODO-rotate-before-release-please",
]


@pytest.mark.parametrize("value", MID_WORD_SECRETS)
def test_placeholder_word_inside_the_value_does_not_hide_a_secret(value: str) -> None:
    assert cec.looks_cred_val(value) is True


@pytest.mark.parametrize("value", LEADING_PLACEHOLDERS)
def test_leading_placeholder_token_stays_a_placeholder(value: str) -> None:
    assert cec.looks_cred_val(value) is False


def test_tracked_example_files_stay_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard must report no credential in the tracked ``.example``/``.template`` files."""
    monkeypatch.chdir(REPO_ROOT)
    assert cec.main() == 0


# ---------------------------------------------------------------------------
# DIG-50 defect 2: punctuation-bearing secrets were invisible to the guard.
#
# ``CRED_VALUE_PATTERNS`` and the ``^[A-Za-z0-9_\-.]{32,}$`` fallback whitelisted
# three narrow character classes. Any credential holding a character outside them
# fell through every shape test and was reported clean. Measured on the merged
# guard, all four values in ``PUNCTUATION_SECRETS`` returned
# ``looks_cred_val(value) is False``.
#
# The shape test must score the value's own character distribution instead of
# whitelisting character classes, so that ``&`` and dictionary-word structure are
# both in scope. It must stay narrow enough that an inline comment and a
# leading-token placeholder are still not reported.
#
# Shannon entropy alone does NOT separate these two groups. Measured bits per
# character: ``Tr0ub4dor&3xyzQ7Lp`` 4.06, ``aB3&x7Kq9ZmTp2Rw`` 4.00,
# ``correct-horse-9-Battery-S7`` 3.57, ``my_secret_passphrase_2024_ok`` 3.78 --
# against the live inline comment ``# https://openrouter.ai - ...`` at 4.35 and
# ``# https://console.x.ai`` at 4.01. A threshold low enough to catch the weakest
# probe also catches both comments. The gates must therefore be ordered:
# anchored placeholder match first, then the inline-comment exclusion, and only
# then the entropy score.
# ---------------------------------------------------------------------------

#: Credentials that are 16 characters or longer and hold at least one character
#: outside every class the old patterns whitelisted. Each must be reported.
PUNCTUATION_SECRETS = [
    "Tr0ub4dor&3xyzQ7Lp",
    "aB3&x7Kq9ZmTp2Rw",
    "correct-horse-9-Battery-S7",
    "my_secret_passphrase_2024_ok",
]

#: Inline comments carried in a ``KEY = ... # comment`` line. These two are live in
#: ``.env.example`` today and score above most probes on entropy alone, so the
#: shape test has to reject them structurally rather than by score.
COMMENT_VALUES = [
    "# https://console.x.ai",
    "# https://openrouter.ai - LiteLLM maps unprefixed house slugs to openrouter/<slug>",
]


@pytest.mark.parametrize("value", PUNCTUATION_SECRETS)
def test_punctuation_bearing_secret_is_in_scope(value: str) -> None:
    assert cec.looks_cred_val(value) is True


@pytest.mark.parametrize("value", COMMENT_VALUES)
def test_inline_comment_value_is_not_a_secret(value: str) -> None:
    assert cec.looks_cred_val(value) is False
