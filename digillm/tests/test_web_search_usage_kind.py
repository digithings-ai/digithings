"""Cost-split lock-in: web-search tool vs grounding telemetry stay distinct (#3853)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from openai.types.chat import ChatCompletion
from openai.types.chat import ChatCompletionMessage as OpenAIMessage
from openai.types.chat.chat_completion import Choice

import digillm
from digillm import client as client_mod
from digillm.telemetry import CallPurpose


def test_purposes_exist() -> None:
    assert CallPurpose.WEB_SEARCH.value == "web_search"
    assert CallPurpose.WEB_GROUNDING.value == "web_grounding"


def test_tool_and_rewrite_purposes_stay_distinct() -> None:
    assert CallPurpose.WEB_SEARCH is not CallPurpose.WEB_GROUNDING
    assert CallPurpose.WEB_SEARCH.value != CallPurpose.WEB_GROUNDING.value


@pytest.fixture()
def usage_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    previous = client_mod._usage_observer
    digillm.set_usage_observer(lambda **fields: records.append(fields))
    yield records
    digillm.set_usage_observer(previous)


def _completion(content: str) -> ChatCompletion:
    return ChatCompletion(
        id="cmpl-web-search-kind",
        created=0,
        model="served-model",
        object="chat.completion",
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=OpenAIMessage(role="assistant", content=content),
            )
        ],
    )


def _run_completion(usage_kind: str, marker: str) -> None:
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _completion(f"grounded {marker}")
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion(
            "gpt-4o-mini",
            [{"role": "user", "content": f"web search probe {marker}"}],
            usage_kind=usage_kind,
        )


def test_completion_records_web_search_kind(
    usage_records: list[dict[str, Any]],
) -> None:
    _run_completion("web_search", "tool-path")
    assert [record["kind"] for record in usage_records] == ["web_search"]


def test_completion_passthrough_preserves_default_chat_kind(
    usage_records: list[dict[str, Any]],
) -> None:
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _completion("hello")
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "plain chat probe"}])
    assert [record["kind"] for record in usage_records] == ["chat"]
