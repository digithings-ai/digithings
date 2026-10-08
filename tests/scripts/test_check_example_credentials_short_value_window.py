"""The 9-to-11-character window under a credential name (DIG-149).

DIG-119 set ``CRED_MIN_VALUE_LEN = 12``, which left the bottom of the
brief's window open: an opaque, non-placeholder value of 9 to 11 characters
under a credential-named variable reported clean. Dropping the floor to 9 for
every credential name would make every 9-to-11-character ordinary word a
finding, because ``is_placeholder()`` covers a short fixed word list and not
words like ``warehouse`` or ``infinite``. This guard fails the pull request,
so a false positive blocks whichever developer wrote one.

So the floor drops only where the variable name corroborates it. A *strong*
credential name (``*_API_KEY``, ``*_SECRET``) is evidence on its own; the
weaker names in ``CRED_VAR_PATTERNS`` (``*_PASSWORD``, ``*_TOKEN``, ...)
carry the same word-shaped false-positive risk and keep the 12 floor.

Every probe below is synthetic, built from the consonant/digit alphabet the
DIG-119 contract uses. No credential value appears in this file.
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / 'scripts' / 'check_example_credentials.py'
_spec = importlib.util.spec_from_file_location('cec', SCRIPT)
cec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cec)

pytestmark = pytest.mark.unit

#: One opaque value per length in the open window. 9 is the floor: `postgres`
#: is 8 and must stay clean, so no bound can sit below it.
SHORT_WINDOW = ['7qk3mz92w', 'x7q2m9z4wb', 'kq93mz7xw2b']

#: A strong credential name corroborates the value. `CLIENT_SECRET` and
#: `WEBHOOK_SECRET` are in `CRED_VAR_PATTERNS` too, and must be reached
#: through `SECRET` rather than through a third pattern.
STRONG_VARS = [
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'API_KEY',
    'STRIPE_SECRET',
    'CLIENT_SECRET',
    'WEBHOOK_SECRET',
]

#: The weaker credential names in `CRED_VAR_PATTERNS`. These are the false
#: positives the narrowing exists for: a 10-character value here is as likely
#: to be an ordinary word as a key, so the floor stays at 12.
WEAK_VARS = [
    'DB_PASSWORD',
    'ADMIN_PASSWORD',
    'SESSION_TOKEN',
    'ACCESS_TOKEN',
    'REFRESH_TOKEN',
    'SIGNING_KEY',
    'PRIVATE_KEY',
]


@pytest.mark.parametrize('value', SHORT_WINDOW)
@pytest.mark.parametrize('var', STRONG_VARS)
def test_short_opaque_value_under_a_strong_credential_name_is_reported(var, value):
    assert cec.looks_cred_val(value, var) is True


@pytest.mark.parametrize('value', SHORT_WINDOW)
@pytest.mark.parametrize('var', WEAK_VARS)
def test_short_opaque_value_under_a_weak_credential_name_is_not_reported(var, value):
    assert cec.looks_cred_val(value, var) is False


def test_the_window_is_closed_with_no_variable_name():
    """A bare value carries no corroboration, so the old floor still applies."""
    for value in SHORT_WINDOW:
        assert cec.looks_cred_val(value) is False


def test_eight_characters_stay_clean_under_a_strong_credential_name():
    """`postgres` is 8, and it is why the floor cannot go below 9.

    The other three are the ordinary words DIG-149 named as the false-positive
    risk. All four measure 8, which puts them below the window rather than in
    it - worth recording, because it means the words the brief worried about
    were never the ones an unconditional drop to 9 would have caught.
    """
    for value in ('postgres', 'changeit', 'readonly', 'internal', 'infinite'):
        assert len(value) == 8
        assert cec.looks_cred_val(value, 'OPENAI_API_KEY') is False


def test_an_ordinary_word_under_a_strong_name_is_the_accepted_trade_off():
    """The narrowing rests on the name, not on a word list.

    This is option 3 as briefed: option 2 (drop the floor for every credential
    name and extend `is_placeholder()`'s word list) was not taken, so nothing
    exempts `warehouse` or `supersecret` under an `*_API_KEY` line. That is
    deliberate - a developer who writes `OPENAI_API_KEY=warehouse` has made a
    mistake either way - and it is pinned here so a later reader does not
    "fix" it as a bug and quietly re-open the window. The same word under a
    weak name is still clean, which is where the false positives went.
    """
    for value in ('warehouse', 'supersecret'):
        assert cec.looks_cred_val(value, 'OPENAI_API_KEY') is True
        assert cec.looks_cred_val(value, 'DB_PASSWORD') is False


def test_short_placeholders_stay_clean_under_a_strong_credential_name():
    """The fixed word list keeps working at the lower floor."""
    for value in ('digichat', 'local', 'dev', 'development', 'test', 'localhost', 'none'):
        assert cec.looks_cred_val(value, 'OPENAI_API_KEY') is False


def test_short_prose_stays_clean_under_a_strong_credential_name():
    """Whitespace or a leading `#` marks a comment, at either floor."""
    assert cec.looks_cred_val('# console', 'OPENAI_API_KEY') is False
    assert cec.looks_cred_val('# todo: add', 'OPENAI_API_KEY') is False
    assert cec.looks_cred_val('not a key', 'OPENAI_API_KEY') is False


def test_single_argument_call_still_reports_the_dig_119_probes():
    """DIG-119's fences call `looks_cred_val` with one argument."""
    for value in ('69qm52xx9xb7', '5nx2m7mzqm5zqmqq', '9z63367327xqzbz426',
                  '8391274650391847562'):
        assert cec.looks_cred_val(value) is True
    for value in ('', 'x', 'admin', 'postgres', 'local', 'digichat', 'your-api-key',
                  'your-litellm-key-here', 'replace-with-openssl-rand-base64-32',
                  '# https://console.x.ai'):
        assert cec.looks_cred_val(value) is False


def test_the_twelve_char_floor_is_unchanged_for_weak_names():
    """Narrowing the floor must not weaken recall at or above 12."""
    assert cec.looks_cred_val('69qm52xx9xb7', 'DB_PASSWORD') is True


def test_tracked_example_files_stay_clean_with_the_window_closed(monkeypatch):
    """PR #5030's scrub must not be re-broken by the lower floor."""
    monkeypatch.chdir(REPO_ROOT)
    assert cec.main() == 0
