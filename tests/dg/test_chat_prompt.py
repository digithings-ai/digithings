"""Unit tests for OpenAI-compat → workflow prompt flattening."""

from __future__ import annotations

import pytest
from digigraph.chat_prompt import messages_to_workflow_prompt
from digigraph.models import ChatMessage


@pytest.mark.unit
def test_single_user_message_is_plain_content() -> None:
    prompt = messages_to_workflow_prompt([ChatMessage(role="user", content="search for X")])
    assert prompt == "search for X"


@pytest.mark.unit
def test_multi_turn_includes_assistant_replies() -> None:
    prompt = messages_to_workflow_prompt(
        [
            ChatMessage(role="user", content="What is digigraph?"),
            ChatMessage(role="assistant", content="digigraph is the orchestration hub."),
            ChatMessage(role="user", content="Say more about that."),
        ]
    )
    assert "User: What is digigraph?" in prompt
    assert "Assistant: digigraph is the orchestration hub." in prompt
    assert "User: Say more about that." in prompt
    # Prior bug: only user turns were joined, so assistant text was absent.
    assert "orchestration hub" in prompt


@pytest.mark.unit
def test_empty_messages_yield_empty_prompt() -> None:
    assert messages_to_workflow_prompt([]) == ""


@pytest.mark.unit
def test_system_messages_are_omitted() -> None:
    prompt = messages_to_workflow_prompt(
        [
            ChatMessage(role="system", content="You are helpful."),
            ChatMessage(role="user", content="hi"),
        ]
    )
    assert prompt == "hi"
    assert "You are helpful" not in prompt


@pytest.mark.unit
def test_long_history_is_trimmed_to_token_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """A long multi-turn history must not grow the flattened prompt unbounded — with a
    small token budget, the oldest turns must be dropped while the most recent exchange
    survives intact."""
    monkeypatch.setenv("DIGI_CHAT_HISTORY_MAX_TOKENS", "30")
    messages = [
        ChatMessage(role="user", content="turn one is old and should get dropped " * 10),
        ChatMessage(role="assistant", content="ack one " * 10),
        ChatMessage(role="user", content="turn two, also old " * 10),
        ChatMessage(role="assistant", content="ack two " * 10),
        ChatMessage(role="user", content="most recent question"),
    ]
    prompt = messages_to_workflow_prompt(messages)
    assert "most recent question" in prompt
    assert "turn one is old" not in prompt


@pytest.mark.unit
def test_non_numeric_history_max_tokens_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Finding 5 (MINOR, final whole-branch review): a non-numeric
    DIGI_CHAT_HISTORY_MAX_TOKENS (e.g. a typo'd env value) must not raise ValueError
    out of int() and abort the whole flatten -- fall back to the default budget and
    log a warning instead."""
    monkeypatch.setenv("DIGI_CHAT_HISTORY_MAX_TOKENS", "not-a-number")
    messages = [
        ChatMessage(role="user", content="turn one"),
        ChatMessage(role="assistant", content="ack one"),
        ChatMessage(role="user", content="most recent question"),
    ]
    prompt = messages_to_workflow_prompt(messages)
    assert "most recent question" in prompt
    assert "not a valid integer" in caplog.text


@pytest.mark.unit
def test_short_history_is_unaffected_by_trimming() -> None:
    """A short history well under the token budget must pass through byte-identical to
    today's behavior — trimming must never rewrite content it didn't need to drop."""
    messages = [
        ChatMessage(role="user", content="What is digigraph?"),
        ChatMessage(role="assistant", content="digigraph is the orchestration hub."),
    ]
    prompt = messages_to_workflow_prompt(messages)
    assert "User: What is digigraph?" in prompt
    assert "Assistant: digigraph is the orchestration hub." in prompt


@pytest.mark.unit
def test_tool_role_messages_are_silently_omitted_today() -> None:
    """Documents the current, deliberate simplification: digichat never sends role="tool"
    history to digigraph today (verified: frontend/digichat/src/lib/adapters/digithings/
    never constructs one), so dropping it here is a right-sized simplification, not
    silent data loss. If this test starts failing because a real caller DOES send
    tool-role turns, chat_prompt.py needs real tool-turn support (see its module
    docstring) — not a tweak to this test."""
    messages = [
        ChatMessage(role="user", content="call the tool"),
        ChatMessage(role="tool", content="tool result content"),
        ChatMessage(role="assistant", content="here is my answer"),
    ]
    prompt = messages_to_workflow_prompt(messages)
    assert "tool result content" not in prompt


@pytest.mark.unit
def test_assistant_only_turns_after_filtered_user_turn_are_not_silently_dropped() -> None:
    """Regression test: trim_messages(start_on="human") returns [] when there is no
    user/human turn to anchor on -- e.g. a whitespace-only user turn gets filtered out
    upstream (role not in the empty-content check), leaving only an assistant turn.
    _trim_to_budget must fall back to the untrimmed turns rather than silently emptying
    real content."""
    messages = [
        ChatMessage(role="user", content="   "),
        ChatMessage(role="assistant", content="reply"),
    ]
    prompt = messages_to_workflow_prompt(messages)
    assert "reply" in prompt


@pytest.mark.unit
def test_last_user_turn_keeps_a_plain_single_turn() -> None:
    from digigraph.chat_prompt import last_user_turn

    assert last_user_turn("RS256 token exchange") == "RS256 token exchange"
    assert last_user_turn("") == ""
    assert last_user_turn("User: this is the actual query") == "User: this is the actual query"


@pytest.mark.unit
def test_last_user_turn_extracts_current_turn_from_flattened_history() -> None:
    from digigraph.chat_prompt import last_user_turn, messages_to_workflow_prompt

    prompt = messages_to_workflow_prompt(
        [
            ChatMessage(role="user", content="What is RS256?"),
            ChatMessage(role="assistant", content="RS256 is an asymmetric signing algorithm."),
            ChatMessage(role="user", content="RS256 token exchange"),
        ]
    )
    assert last_user_turn(prompt) == "RS256 token exchange"
