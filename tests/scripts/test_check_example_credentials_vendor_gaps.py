"""DIG-550: vendor prefixes outside the list, and an ``sk-`` body on standard base64.

Two gaps that DIG-112 (PR #5049, merged as ``6f17728c8``) left open on its merge
card. Both are in the vendor loop of ``looks_cred_val()``, and both are invisible
to CI because the tracked-corpus fence stays green over each of them.

**Gap 1 - a prefix that is not in the list never matches.** ``CRED_VALUE_PATTERNS``
held four entries, so ``sk_live_``, ``AIza``, ``AKIA`` and ``hf_`` were reported
clean. Measured on ``ea6cd7317`` (``origin/feat/50-credential-guard-shape``, with
DIG-119 merged), all four bare keys score 4.12 to 5.11 bits per character, so the
entropy floor reports them anyway. Every one of them read *clean* the moment a
``# comment`` followed the key:

    prefix    len  bits/char  bare   bare + " # rotated 2026-01"
    sk_live_   31      4.825   True   False
    AIza       36      5.059   True   False
    AKIA       20      4.122   True   False
    hf_        36      5.114   True   False

That is the whole case for a prefix here, and it is the same case DIG-112 made for
the four it added: ``looks_cred_val`` rejects any value holding whitespace *before*
it takes a score, so a value carrying an inline comment never reaches the entropy
floor. The vendor loop is the only gate that can see it.

**Gap 2 - an ``sk-`` body built on standard base64 stops matching at the first
``+`` or ``/``.** The body class was ``[A-Za-z0-9_-]``, which is URL-safe base64.
The bare value is reported (the prefix loop misses it, the entropy floor catches it
at 4.755 bits per character), but with a trailing comment the floor is unreachable
and the value is reported clean.

Each new entry therefore states the alphabet and minimum length the vendor really
uses, rather than a bare prefix. That is not decoration - it is what keeps the
placeholders developers actually write out of the findings. Four currently-clean
values turn into findings under a bare-prefix design, and stay clean under a body
class:

    hf_replace_me_with_token # add the real token
    AKIA_REPLACE_ME_NOT_A_KEY # example only
    AIza_REPLACE_ME # Google Cloud key
    sk_live_replace_me # Stripe key

``+`` and ``/`` go into the ``sk-`` body class only. Widened across every prefix, a
``/`` would sit in prose on any value that reached the loop, which is how the
generic character-class patterns DIG-112 removed came back in the first place.

Kept in its own file, the way DIG-112 kept its tests, so neither
``test_check_example_credentials.py`` (the pinned contract) nor
``test_check_example_credentials_vendor_prefixes.py`` has to move. Every value here
is **synthetic**: bodies are built to each vendor's documented shape and length
from the alphabet ``qwzxvbnm2345679`` and mixed-case equivalents. None came from git
history and none is a real key.
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
        "check_example_credentials_vendor_gaps_under_test", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cec = _load_module()

#: A trailing inline comment, as carried by a live ``KEY = ... # comment`` line.
TRAILING_COMMENT = " # rotated 2026-01"

#: 24 characters of key body, comfortably past ``sk-``'s {20,} minimum.
ALNUM_BODY = "A1b2C3d4E5f6G7h8I9j0K1l2"

#: ---------------------------------------------------------------------------
# Gap 1: one real key shape per candidate prefix, each built to the length and
# alphabet its vendor documents. The body is what makes the case - a prefix on
# its own would also catch the placeholders in ``FAKE_PREFIXED_VALUES``.
# ---------------------------------------------------------------------------
GAP1_KEYS = {
    "sk_live_": "sk_live_" + "4wRt9QzKm2XvB7Nc1LpZaHd",  # Stripe secret key
    "AIza": "AIza" + "SyD3kLq9TbWm2XzRv7Nc1PgHa6Je0Uf4",  # Google API key
    "AKIA": "AKIA" + "Q7RT2ZM9XB4VDK1N",  # AWS access key id, 16 after the prefix
    "hf_": "hf_" + "Kd9QrTzXm3Vb7NwLp2Jc5Hs1Ae6Ug0Yf4",  # HuggingFace token
}

#: ---------------------------------------------------------------------------
# The same four prefixes on a body that is not a key. These are the shapes a
# developer writes in an ``.example`` file, and each one is clean today. They are
# checked through ``CRED_VALUE_PATTERNS`` rather than ``looks_cred_val`` because the
# entropy path reports the *bare* forms of some of them - a pre-existing
# consequence of the ``CRED_MIN_VALUE_LEN`` floor, not of anything in this leaf.
# ---------------------------------------------------------------------------
FAKE_PREFIXED_VALUES = [
    "sk_live_replace_me",
    "AIza_REPLACE_ME",
    "AKIA_REPLACE_ME_NOT_A_KEY",
    "hf_replace_me_with_token",
]

#: The same four, carrying the inline comment that makes the entropy floor
#: unreachable. Clean today; a bare prefix would report all four.
FAKE_PREFIXED_COMMENTS = [
    "sk_live_replace_me # Stripe key",
    "AIza_REPLACE_ME # Google Cloud key",
    "AKIA_REPLACE_ME_NOT_A_KEY # example only",
    "hf_replace_me_with_token # add the real token",
]

#: ---------------------------------------------------------------------------
# Gap 2: an ``sk-`` body built on standard base64. ``STANDARD_BASE64_BODY`` holds
# both ``+`` and ``/``, which the URL-safe class stops at.
# ---------------------------------------------------------------------------
STANDARD_BASE64_BODY = "Ab3C+dEf/Gh1IjKlMnOpQrSt"


# ---------------------------------------------------------------------------
# Gap 1
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", GAP1_KEYS.values(), ids=list(GAP1_KEYS))
def test_commented_prefixed_key_is_a_credential(key: str) -> None:
    """A comment after the key must not hide a real prefixed credential.

    Red on ``ea6cd7317`` for all four prefixes: the prose exclusion rejects the
    value before any score is taken, and no pattern in the list carries these
    prefixes.
    """
    assert cec.looks_cred_val(key + TRAILING_COMMENT) is True


@pytest.mark.parametrize("key", GAP1_KEYS.values(), ids=list(GAP1_KEYS))
def test_prefixed_key_without_comment_is_a_credential(key: str) -> None:
    """Control for the test above: the bare key was already caught.

    The gap is the comment, not the prefix. If this ever fails, the prefix was
    over-broad enough to change a bare value, which is a different defect.
    """
    assert cec.looks_cred_val(key) is True


@pytest.mark.parametrize("key", GAP1_KEYS.values(), ids=list(GAP1_KEYS))
def test_prefix_not_the_score_is_what_catches_a_commented_key(key: str) -> None:
    """Pin *why* each prefix earns its place, as an executable claim.

    ``looks_cred_val`` returns ``False`` for any value holding whitespace before
    it scores anything, so a verdict of ``True`` on a value that holds whitespace
    can only have come from the vendor loop. The precondition is asserted first so
    that the claim cannot pass for the wrong reason: if the guard ever scores
    whitespace-bearing values, this test fails instead of quietly ceasing to prove
    anything.
    """
    commented = key + TRAILING_COMMENT
    assert any(c.isspace() for c in commented), (
        "the value must carry whitespace, or the score can reach it and this "
        "test no longer shows the prefix is load-bearing"
    )
    assert cec.looks_cred_val(commented) is True


@pytest.mark.parametrize("value", FAKE_PREFIXED_VALUES)
def test_prefixed_placeholder_is_not_matched_by_the_vendor_loop(value: str) -> None:
    """A prefix plus a placeholder body must not reach the vendor loop.

    Checked against the pattern list rather than ``looks_cred_val``, so a verdict
    from the entropy path cannot mask a bare prefix that is too greedy.
    """
    matching = [p for p in cec.CRED_VALUE_PATTERNS if re.match(p, value)]
    assert matching == [], f"{value!r} matched the vendor loop via {matching}"


@pytest.mark.parametrize("value", FAKE_PREFIXED_COMMENTS)
def test_commented_prefixed_placeholder_is_not_a_credential(value: str) -> None:
    """The fence above, with the comment that makes it a live example-file line.

    This is the shape a bare prefix would turn into a finding. It is clean today
    and has to stay clean.
    """
    assert cec.looks_cred_val(value) is False


# ---------------------------------------------------------------------------
# Gap 2
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value",
    [
        "sk-" + STANDARD_BASE64_BODY,  # bare, already caught by the score
        "sk-" + STANDARD_BASE64_BODY + TRAILING_COMMENT,  # the gap
        "sk-" + STANDARD_BASE64_BODY + "=" + TRAILING_COMMENT,  # and padded
    ],
)
def test_standard_base64_sk_body_is_a_credential(value: str) -> None:
    """An ``sk-`` body using ``+`` or ``/`` must survive a trailing comment.

    Red on ``ea6cd7317`` for the two commented forms: ``[A-Za-z0-9_-]`` is
    URL-safe base64, so matching stopped at the first ``+``, three characters in.
    The bare form is the control and is already caught.
    """
    assert cec.looks_cred_val(value) is True


@pytest.mark.parametrize("key_shape", ["sk-", "sk-proj-", "sk-ant-api03-"])
def test_widened_sk_class_keeps_the_real_sk_families(key_shape: str) -> None:
    """Adding ``+`` and ``/`` must not cost the hyphen the vendor families use.

    Both real families put a ``-`` inside the first 20 characters, so dropping ``-``
    from the widened class breaks them silently - they read clean, nothing fails,
    and the corpus fence stays green. Found the same way twice while building this.
    """
    assert cec.looks_cred_val(key_shape + ALNUM_BODY + TRAILING_COMMENT) is True


def test_only_the_sk_entry_carries_standard_base64_characters() -> None:
    """Pin the boundary on the widening.

    ``+`` and ``/`` belong in the ``sk-`` body class and nowhere else. Applied
    across every prefix they would sit in prose on any value that reached the loop,
    which is how the generic character-class patterns DIG-112 removed came back.
    """
    widened = [
        p
        for p in cec.CRED_VALUE_PATTERNS
        if ("+" in p or "/" in p) and not p.startswith("^sk-")
    ]
    assert widened == [], f"standard-base64 characters outside the sk- entry: {widened}"


@pytest.mark.parametrize(
    "body",
    [
        ALNUM_BODY[:19],  # 19 plain characters
        STANDARD_BASE64_BODY[:19],  # 19, and three of them are the new characters
    ],
)
def test_widened_sk_class_keeps_its_minimum_key_length(body: str) -> None:
    """Widening the class must not turn ``sk-`` into a prefix-only pattern.

    The second body is the sharper half: it is 19 characters long *and* uses the
    characters the widening adds, so it fails unless the length floor is applied to
    the widened class rather than alongside it. Sliced from the constant so a
    future edit to it cannot silently turn this into a 21-character case; the
    length is asserted rather than assumed.
    """
    assert len(body) == 19, f"fence body drifted to {len(body)} characters"
    matching = [p for p in cec.CRED_VALUE_PATTERNS if re.match(p, "sk-" + body)]
    assert matching == [], f"sk- matched a 19-character body via {matching}"
    matching = [p for p in cec.CRED_VALUE_PATTERNS if re.match(p, "sk-" + ALNUM_BODY)]
    assert matching, "sk- no longer matches a 24-character key body"


# ---------------------------------------------------------------------------
# Structural fences on the whole list
# ---------------------------------------------------------------------------
def test_no_vendor_pattern_is_end_anchored() -> None:
    """Every entry, including the four added here, must stay end-anchor free.

    An end anchor is what let a trailing comment hide a prefixed key - the reason
    the commented-value tests above can pass at all. This is a backstop behind them.
    """
    end_anchored = [p for p in cec.CRED_VALUE_PATTERNS if p.endswith(("$", r"\Z"))]
    assert end_anchored == [], f"end-anchored vendor pattern(s): {end_anchored}"


def test_tracked_example_files_stay_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real regression gate: the guard must still exit 0 on the tracked files.

    The 18 tracked ``.example`` / ``.template`` files carry placeholder bodies
    under credential names, and ``.env.example`` carries three live ``sk-``
    comments. None of the four candidate prefixes appears anywhere in the corpus,
    so this asserts the absence of a false positive rather than the presence of a
    detection - the detection half is the parametrised tests above.
    """
    monkeypatch.chdir(REPO_ROOT)
    assert cec.main() == 0