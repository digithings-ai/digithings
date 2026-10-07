"""Counsel's DIG-1251 condition 3: the environment denylist is deny-only.

Counsel approved the env-denylist shape on four conditions. This file proves
condition 3 — "a **test** that every ``REFUSED_TOOLS`` entry is still refused
with the variable set to every legal value", explicitly "not a log line" — and
the deny-only structure that condition 1 depends on.

Two directions are pinned on purpose:

* **The floor holds.** Every member of ``REFUSED_TOOLS`` stays refused under
  *every* legal value of the variable, including adversarial negations. This is
  Counsel's condition 3.
* **The layer works.** The variable still *adds* refusals. Without this, a
  ``env_denied_tools()`` that ignored the environment entirely would pass the
  floor tests vacuously while shipping a knob that does nothing.
"""

from __future__ import annotations

import pytest
from digiquant.tool_refusals import (
    ENV_DENYLIST_VAR,
    REFUSED_TOOLS,
    env_denied_tools,
    is_refused,
    refusal_message,
)

#: Every legal value of the variable, including the ones that look like they
#: might un-refuse something. Counsel's condition 3 asks for "every legal value",
#: so adversarial strings are included deliberately — each must fail to permit.
LEGAL_ENV_VALUES: tuple[str | None, ...] = (
    None,  # unset
    "",  # empty
    "   ",  # whitespace only
    "\t\n\r ",  # every whitespace char, no token
    "digifetch_congress_trades",  # the refused name itself
    "DIGIFETCH_CONGRESS_TRADES",  # upper case
    "Digifetch_Congress_Trades",  # mixed case
    "digifetch_congress_trades,digifetch_other",  # comma list
    "digifetch_congress_trades;digifetch_other",  # semicolon list
    "digifetch_congress_trades digifetch_other",  # space list
    "digifetch_congress_trades\ndigifetch_other",  # newline list
    ",,,digifetch_congress_trades,,,",  # leading/trailing separators
    # Apparent negations. There is no un-refuse syntax, so these are all just
    # unknown tokens and none of them may permit the feed.
    "-digifetch_congress_trades",
    "!digifetch_congress_trades",
    "allow=digifetch_congress_trades",
    "unrefuse=digifetch_congress_trades",
    "allow",
    "allow digifetch_congress_trades",
    "DIGIQUANT_REFUSED_TOOLS=",
    "none",  # a plausible "no denylist" word, which must not mean "empty"
    "null",
    "false",
    "0",
    "*",  # a glob must not widen into permitting anything
    "**",
    ".",  # a dot must not match "any tool"
    "..",
    "digifetch_",  # prefix
    "digifetch_congress",  # shorter prefix
    "digifetch_congress_trades_extra",  # longer name is a different tool
    "DIGIFETCH_CONGRESS_TRADES ",  # trailing space
    " digifetch_congress_trades",  # leading space
    "éèê",  # non-ascii
    "x" * 10_000,  # very long single token
    ",".join(["digifetch_a"] * 500),  # very long list
)


def _set_env(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    """Set or unset the denylist variable for the duration of a test."""
    if value is None:
        monkeypatch.delenv(ENV_DENYLIST_VAR, raising=False)
    else:
        monkeypatch.setenv(ENV_DENYLIST_VAR, value)


@pytest.mark.parametrize("value", LEGAL_ENV_VALUES, ids=repr)
def test_code_constant_floor_holds_for_every_legal_env_value(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """Counsel condition 3: no legal value of the variable permits a refusal."""
    _set_env(monkeypatch, value)
    assert REFUSED_TOOLS, "the floor must not be empty for this test to mean anything"
    for name in REFUSED_TOOLS:
        assert is_refused(name) is True, (
            f"{name!r} must stay refused with {ENV_DENYLIST_VAR}={value!r}"
        )


def test_the_refused_feed_is_specifically_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name the tool this issue exists for, so a rename cannot hide the pin."""
    for value in LEGAL_ENV_VALUES:
        _set_env(monkeypatch, value)
        assert is_refused("digifetch_congress_trades") is True, value


@pytest.mark.parametrize("value", LEGAL_ENV_VALUES, ids=repr)
def test_ordinary_tools_are_never_refused_by_the_variable(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """A denylist value must not sweep in unrelated tools.

    Guards the opposite failure: a too-greedy parser that treated a token as a
    prefix, glob or wildcard would refuse tools Counsel never named.
    """
    _set_env(monkeypatch, value)
    for name in ("digifetch_quote", "digifetch_sec_filings", "digiquant_list_strategies"):
        assert is_refused(name) is False, f"{name!r} wrongly refused by {value!r}"


def test_the_variable_adds_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The additive direction works — otherwise the knob does nothing."""
    _set_env(monkeypatch, None)
    assert is_refused("digifetch_some_other_tool") is False
    _set_env(monkeypatch, "digifetch_some_other_tool")
    assert is_refused("digifetch_some_other_tool") is True
    assert "digifetch_some_other_tool" in env_denied_tools()


def test_the_variable_accepts_every_documented_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Comma, semicolon and whitespace all separate entries."""
    for sep in (",", ";", " ", "\t", "\n", "\r"):
        _set_env(monkeypatch, f"digifetch_a{sep}digifetch_b")
        assert env_denied_tools() == {"digifetch_a", "digifetch_b"}, sep


def test_fails_closed_on_missing_empty_and_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counsel condition 2: absent or blank values add nothing, and do not raise."""
    for value in (None, "", " ", "\t\n", ",", ";,", ",,; ,;"):
        _set_env(monkeypatch, value)
        assert env_denied_tools() == frozenset(), repr(value)
        assert is_refused("digifetch_congress_trades") is True, repr(value)


def test_unparseable_value_raises_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed value yields tokens, never an exception past the refusal check."""
    for value in ("%20%2C", "a=b;c=d", "ünïcödé", "\x01\x02", "  "):
        _set_env(monkeypatch, value)
        env_denied_tools()  # must not raise
        assert is_refused("digifetch_congress_trades") is True, repr(value)


def test_case_insensitive_match_only_adds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Case folding can only refuse more names, never fewer."""
    _set_env(monkeypatch, "DIGIFETCH_SOME_OTHER_TOOL")
    assert is_refused("digifetch_some_other_tool") is True
    _set_env(monkeypatch, "")
    assert is_refused("digifetch_some_other_tool") is False


def test_refusal_message_is_stable_and_names_the_code() -> None:
    """Callers branch on the typed code; the message must keep carrying it."""
    message = refusal_message("digifetch_congress_trades")
    assert "tool_refused" in message
    assert "digifetch_congress_trades" in message
    assert "Do not retry" in message
