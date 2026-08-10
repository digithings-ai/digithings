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
