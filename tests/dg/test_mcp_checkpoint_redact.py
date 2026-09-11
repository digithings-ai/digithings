"""MCP OAuth token redaction before checkpointer write (#3794)."""

from __future__ import annotations

from typing import Any

import pytest
from digigraph.graph.mcp_checkpoint_redact import (
    McpTokenRedactingCheckpointer,
    redact_checkpoint_mcp_tokens,
    redact_checkpoint_writes,
    redact_mcp_servers_value,
)


@pytest.mark.unit
def test_redact_mcp_servers_value_strips_token_keeps_auth() -> None:
    servers = [
        {"id": "s", "url": "https://mcp.example/mcp", "auth": "oauth", "token": "tok"},
        {"id": "t", "url": "https://mcp.example/other"},
    ]
    out = redact_mcp_servers_value(servers)
    assert out == [
        {"id": "s", "url": "https://mcp.example/mcp", "auth": "oauth"},
        {"id": "t", "url": "https://mcp.example/other"},
    ]
    # original untouched
    assert servers[0]["token"] == "tok"


@pytest.mark.unit
def test_redact_checkpoint_payload_omits_token() -> None:
    fake_token = "tok"
    checkpoint = {
        "v": 1,
        "id": "ckpt-1",
        "channel_values": {
            "prompt": "hi",
            "mcp_servers": [
                {
                    "id": "datatap",
                    "url": "https://mcp.datatap.example/mcp",
                    "auth": "oauth",
                    "token": fake_token,
                }
            ],
        },
    }
    redacted = redact_checkpoint_mcp_tokens(checkpoint)
    payload = redacted["channel_values"]["mcp_servers"]
    assert fake_token not in repr(payload)
    assert "token" not in payload[0]
    assert payload[0]["auth"] == "oauth"
    # in-request original still has the token
    assert checkpoint["channel_values"]["mcp_servers"][0]["token"] == fake_token


@pytest.mark.unit
def test_redact_checkpoint_writes_omits_token() -> None:
    fake_token = "tok"
    writes = [
        ("prompt", "hi"),
        (
            "mcp_servers",
            [{"id": "s", "url": "https://mcp.example/mcp", "token": fake_token}],
        ),
    ]
    out = redact_checkpoint_writes(writes)
    assert fake_token not in repr(out)
    assert "token" not in out[1][1][0]
    assert writes[1][1][0]["token"] == fake_token


@pytest.mark.unit
def test_redacting_checkpointer_put_strips_token_from_durable_payload() -> None:
    fake_token = "secret-token"

    class _FakeSaver:
        def __init__(self) -> None:
            self.checkpoints: list[Any] = []
            self.writes: list[Any] = []

        def put(self, config, checkpoint, metadata, new_versions):
            self.checkpoints.append(checkpoint)
            return config

        def put_writes(self, config, writes, task_id, task_path=""):
            self.writes.append(list(writes))

    inner = _FakeSaver()
    saver = McpTokenRedactingCheckpointer(inner)
    live = {
        "channel_values": {
            "mcp_servers": [{"id": "s", "url": "https://mcp.example/mcp", "token": fake_token}]
        }
    }
    saver.put({"configurable": {"thread_id": "t"}}, live, {}, {})
    assert len(inner.checkpoints) == 1
    stored = inner.checkpoints[0]["channel_values"]["mcp_servers"]
    assert fake_token not in repr(stored)
    assert "token" not in stored[0]
    # in-request state keeps the token
    assert live["channel_values"]["mcp_servers"][0]["token"] == fake_token

    saver.put_writes(
        {"configurable": {"thread_id": "t", "checkpoint_id": "c"}},
        [("mcp_servers", [{"id": "s", "url": "https://mcp.example/mcp", "token": fake_token}])],
        task_id="task-1",
    )
    assert fake_token not in repr(inner.writes[0])
