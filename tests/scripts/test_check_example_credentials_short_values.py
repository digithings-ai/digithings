"""DIG-43: the credential guard's length floor hides short API keys.

``scripts/check_example_credentials.py`` gates a value on **length** twice, and
both gates sit above the length of real keys:

1. ``looks_cred_val()`` returns ``False`` outright for any value shorter than 16
   characters.
2. ``CRED_VALUE_PATTERNS`` then demands 32 alphanumerics, or 20 base64
   characters, or a ``sk-`` / ``ghp_`` / ``gho_`` / ``glpat-`` prefix.

So a value of 16 to 19 opaque characters clears gate 1 and then fails every
pattern in gate 2, and a value of 12 to 15 characters never reaches gate 2 at
all. Both are reported clean. Measured on ``09a05de4a``
(``origin/feat/50-credential-guard-shape``, with the DIG-50 placeholder fix
merged), all four probes in ``SHORT_CREDENTIALS`` returned
``looks_cred_val(value) is False``.

Once the variable name has already matched ``CRED_VAR_PATTERNS``, length is not
evidence of anything: a ``*_API_KEY`` holding a short opaque value is the case
this guard exists to catch. These tests pin that contract, and pin the fences
that stop the floor from being dropped into false positives.

This is DIG-43 (the *length* floor). DIG-50 owns the two *shape* defects in the
same function -- unanchored placeholder matching and punctuation-bearing
secrets -- and owns ``tests/scripts/test_check_example_credentials.py``. This
file is separate on purpose so the two sets of tests cannot conflict.

Every value below is **synthetic**: the flagged probes are built from the
consonant/digit alphabet ``qwzxvbnm2345679`` and the fences are short words,
placeholder forms and inline comments copied from the tracked example files.
No value was taken from git history and none is a real key.
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
        "check_example_credentials_short_values_under_test", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cec = _load_module()

# ---------------------------------------------------------------------------
# Short opaque values that the guard reports clean today. Each sits inside a
# character class the value-shape patterns already accept -- so the only reason
# each one is missed is its length.
#
#   probe                len   Shannon (bits/char)   looks_cred_val on 09a05de4a
#   69qm52xx9xb7          12        3.02                    False
#   5nx2m7mzqm5zqmqq      16        2.75                    False
#   9z63367327xqzbz426    18        3.16                    False
#   8391274650391847562   19        3.30                    False
#
# 16 is the boundary the issue names; 12 forces the floor below the current
# ``len(v) < 16`` early return, and 19 pins the sub-20 window where the base64
# branch is one character short of matching.
# ---------------------------------------------------------------------------
SHORT_CREDENTIALS = [
    "69qm52xx9xb7",
    "5nx2m7mzqm5zqmqq",
    "9z63367327xqzbz426",
    "8391274650391847562",
]

# ---------------------------------------------------------------------------
# Fences. Every one of these is ``False`` on ``09a05de4a`` and must stay
# ``False``: dropping the floor must not turn the tracked example files, or the
# short human-readable values developers actually write, into findings.
#
# ``your-api-key`` is the load-bearing one. Its Shannon score (3.25) is *higher*
# than the 12-character probe's (3.02), so no entropy threshold separates them.
# The only thing that can separate them is the anchored placeholder gate, which
# is why the gates have to run in the order DIG-50 pinned: anchored placeholder
# first, inline-comment exclusion second, any score last.
# ---------------------------------------------------------------------------
SHORT_NON_CREDENTIALS = [
    "",
    "x",
    "admin",
    "postgres",
    "local",
    "digichat",
    "your-api-key",
    "your-litellm-key-here",
    "replace-with-openssl-rand-base64-32",
    "# https://console.x.ai",
    "# https://openrouter.ai - LiteLLM maps unprefixed house slugs to openrouter/<slug>",
]


@pytest.mark.parametrize("value", SHORT_CREDENTIALS)
def test_short_opaque_value_is_in_scope(value: str) -> None:
    """A credential-shaped variable holding a short opaque value must be reported."""
    assert cec.looks_cred_val(value) is True


@pytest.mark.parametrize("value", SHORT_NON_CREDENTIALS)
def test_short_non_credential_value_is_not_reported(value: str) -> None:
    """Short words, placeholder forms and inline comments must stay clean."""
    assert cec.looks_cred_val(value) is False


def test_tracked_example_files_stay_clean_after_the_floor_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real regression gate: the guard must still exit 0 on the tracked files.

    ``.env.example`` and ``infra/digichat-release/*.example`` carry live inline
    comments on ``*_API_KEY`` lines, and ``docs/templates/project/.env.example``
    carries a 21-character key-shaped placeholder. All three are in the band this
    change widens, so this is the test that proves the floor can drop without
    re-breaking the DIG-31 scrub.
    """
    monkeypatch.chdir(REPO_ROOT)
    assert cec.main() == 0