"""DIG-42 leaf B: a vendor key followed by a `# comment` is invisible for every prefix the guard does not know.

`scripts/check_example_credentials.py` rejects prose before it scores anything:

    if v.startswith('#') or any(c.isspace() for c in v):
        return False

`main()` splits each tracked `.example` / `.template` line on the first `=`, so a
value written as `KEY = <secret>  # where it came from` reaches `looks_cred_val`
with the comment still attached. That value carries whitespace, so it is rejected
before `shannon_entropy()` ever runs. **The vendor-prefix loop in
`CRED_VALUE_PATTERNS` is therefore the only gate that can catch a commented
key** - the script's own comment says so.

`CRED_VALUE_PATTERNS` holds four prefixes: `sk-`, `ghp_`, `gho_`, `glpat-`.
Every other real vendor key is therefore clean whenever a comment follows it,
even though the same key is reported the moment the comment is deleted.

Measured on `6f17728c8` (`origin/feat/50-credential-guard-shape`, both DIG-50
leaves merged) through `main()`, on a tracked `.example` file:

    six commented vendor keys, one per missing prefix  ->  exit 0 (all missed)
    the same six with the comments stripped            ->  exit 1 (5 of 6 caught)

This is not an edge case for this repository. `.env.example` is where a
developer pastes a real key *and* writes where they got it, and 12 of its 19
credential-named lines are exactly that shape. It also lands badly with
[DIG-42](/DIG/issues/DIG-42) leaf A: a green CI job that misses these six
certifies less than it appears to, which is the failure mode the whole guard
epic exists to prevent.

The contract pinned here:

  * a vendor key followed by a `# comment` is a credential, for the prefixes
    this file lists - the same property leaf B's
    `test_check_example_credentials_vendor_prefixes.py` pins for the four
    prefixes it already knew about;
  * `sk-` bodies are URL-safe base64, and a standard-alphabet `+` or `/` inside
    one must not hide the key behind a comment either;
  * widening the prefix list must not turn prose into a credential. The fences
    below are copied from the tracked example files and must stay clean.

Kept in its own file so it cannot conflict with the two pinned contracts this
guard already owns (`test_check_example_credentials.py` for DIG-50 leaf A,
`test_check_example_credentials_vendor_prefixes.py` for leaf B). Implementers
must not edit those, or this one.

Every value below is **synthetic**. The flagged probes are built from the
consonant/digit alphabet and reshaped to carry a realistic prefix; the fences are
placeholder forms and inline comments copied from the tracked example files. No
value was taken from git history and none is a real key.
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
        "check_example_credentials_commented_prefixes_under_test", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cec = _load_module()

#: 28 characters of key body, comfortably past every minimum length in play.
BODY = "wZ4qXv9BnT2kLpR7mC3dYhJ6sF1gA"

#: A standard-base64 alphabet, for the `sk-` family. `+` and `/` are the two
#: characters a URL-safe base64 class cannot hold, and `sk-` bodies are
#: URL-safe base64 *by definition*, so a vendor that emits standard base64 puts
#: them inside the first 20 characters.
B64_BODY = "wZ4+qX/v9BnT2kLpR7mC3dYhJ6sF1gA"

#: A trailing inline comment in the shape the tracked example files use.
COMMENT = "  # vendor console"

#: Vendor key shapes absent from `CRED_VALUE_PATTERNS`. Each entry is
#: `(id, value)`. The first five are prefix families the guard has never heard
#: of; the last two are `sk-` bodies carrying a character the current body class
#: cannot hold.
MISSING_PREFIX_KEYS = [
    ("stripe_live", "sk_live_" + BODY),
    ("google_aiza", "AIza" + BODY),
    ("aws_akia", "AKIA" + BODY),
    ("huggingface_hf", "hf_" + BODY),
    ("slack_xoxb", "xoxb-123456789012-1234567890123-" + BODY[:20]),
    ("sendgrid_sg", "SG." + BODY + "-_x"),
    ("sk_standard_b64_plus", "sk-" + B64_BODY),
    ("sk_standard_b64_slash", "sk-" + B64_BODY.replace("+", "/", 1)),
]

#: Prose that must stay clean. Every entry is a value the scanner actually
#: reaches - `main()` skips a line that starts with `#`, so only the *uncommented*
#: credential-named lines in the tracked example files are fences. A prefix list
#: that flags any of these blocks every future pull request.
#:
#: `.env.example:42`'s `sk-your-master-or-virtual-key` is deliberately absent.
#: That line is commented out, so the scanner never sees it, and the `sk-` prefix
#: already reports it today if it is ever uncommented. That is a pre-existing
#: false positive outside this leaf, not something to assert here.
PROSE_FENCES = [
    # .env.example:12 - empty value, description in the comment
    " # https://openrouter.ai - LiteLLM maps unprefixed house slugs to openrouter/<slug>",
    # .env.example:24 - empty value padded with spaces before the comment
    "        # https://console.x.ai",
    # .env.example:118 - the value is a comment, the description is the field name
    "id          # optional: document key (default: id)",
    # .env.example:135 - the Stripe docs' own placeholder spelling
    "sk_test_...",
    # .env.example:18 - a documented prefix that is not a key
    "ci_live_...",
    # .env.example:38 - prose wrapped across three commented lines
    "the same key digigraph should send",
    # The empty value itself, and the usual placeholder spellings.
    "",
    "your-openai-key-here",
    "<your-api-key>",
    "REPLACE_ME",
    "changeme",
]


@pytest.mark.parametrize(
    ("value",),
    [(v,) for _, v in MISSING_PREFIX_KEYS],
    ids=[i for i, _ in MISSING_PREFIX_KEYS],
)
def test_missing_prefix_key_is_in_scope_bare(value):
    """The bare value is already reported; this pins that it stays reported."""
    assert cec.looks_cred_val(value) is True, (
        f"looks_cred_val({value!r}) is False, but this probe is a bare vendor key "
        "with no comment attached. The commented case below is the defect; if "
        "this one is red too, the length or entropy floor moved."
    )


@pytest.mark.parametrize(
    ("value",),
    [(v,) for _, v in MISSING_PREFIX_KEYS],
    ids=[i for i, _ in MISSING_PREFIX_KEYS],
)
def test_missing_prefix_key_is_in_scope_behind_a_comment(value):
    """The defect: prose is rejected before the score, so the prefix loop is the only gate."""
    commented = value + COMMENT
    assert cec.looks_cred_val(commented) is True, (
        f"looks_cred_val({commented!r}) is False. The value carries a trailing "
        f"`# comment`, so the prose exclusion rejects it before the entropy "
        f"score runs and `CRED_VALUE_PATTERNS` is the only gate left. The bare "
        f"form {value!r} is reported, so nothing about the key itself hides it - "
        "only the comment does."
    )


@pytest.mark.parametrize(("prose",), [(p,) for p in PROSE_FENCES])
def test_widening_the_prefix_list_does_not_flag_prose(prose):
    """The fence: prose under a credential name must stay clean."""
    assert cec.looks_cred_val(prose) is False, (
        f"looks_cred_val({prose!r}) is True. This is prose from a tracked "
        "example file. Flagging it blocks every future pull request, so the "
        "prefix list has to stay a list of vendor prefixes rather than a "
        "general shape rule."
    )


@pytest.mark.parametrize(
    ("var",),
    [("OPENROUTER_API_KEY",), ("XAI_API_KEY",), ("STRIPE_SECRET_KEY",)],
)
def test_tracked_credential_named_lines_stay_clean(var):
    """The live corpus: every credential-named line in `.env.example` is empty or prose.

    Pinned by name rather than by reading the file, so a future edit to
    `.env.example` cannot silently make this test vacuous.
    """
    assert cec.looks_cred_var(var) is True, (
        f"looks_cred_var({var!r}) is False, so this variable is out of scope and "
        "the fence above is testing nothing for it."
    )