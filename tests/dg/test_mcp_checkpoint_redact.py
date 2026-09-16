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
def test_redact_mcp_servers_value_strips_nested_denylisted_keys_keeps_public() -> None:
    """Any secret-named key (not just ``token``) is stripped, recursively (#3969)."""
    servers = [
        {
            "id": "s",
            "url": "https://mcp.example/mcp",
            "auth": "oauth",
            "authorization": "Bearer top-level",
            "api_key": "key-123",
            "client_secret": "cs-456",
            "headers": {"Authorization": "Bearer nested", "X-Trace": "keep"},
            "auth_config": {"type": "oauth", "client_secret": "nested-cs"},
            "items": [{"refresh_token": "rt-789", "label": "keep"}],
        }
    ]
    out = redact_mcp_servers_value(servers)
    assert out == [
        {
            "id": "s",
            "url": "https://mcp.example/mcp",
            "auth": "oauth",
            "headers": {"X-Trace": "keep"},
            "auth_config": {"type": "oauth"},
            "items": [{"label": "keep"}],
        }
    ]
    # in-request original still carries the secrets
    assert servers[0]["authorization"] == "Bearer top-level"
    assert servers[0]["headers"]["Authorization"] == "Bearer nested"
    assert servers[0]["auth_config"]["client_secret"] == "nested-cs"
    assert servers[0]["items"][0]["refresh_token"] == "rt-789"


@pytest.mark.unit
def test_redact_mcp_servers_value_strips_hyphenated_secret_keys() -> None:
    """Wire-style hyphenated header names are normalized before matching (#3969).

    ``X-API-Key`` is the codebase's own example auth header (``models.py``), so it
    must not sneak a secret past a denylist that only knows ``api_key``.
    """
    servers = [
        {
            "id": "s",
            "url": "https://mcp.example/mcp",
            "X-API-Key": "key-123",
            "headers": {
                "x-api-key": "lower-key",
                "X-Auth-Token": "auth-tok",
                "x-client-secret": "cs-456",
                "X-Trace": "keep",
            },
        }
    ]
    out = redact_mcp_servers_value(servers)
    assert out == [
        {
            "id": "s",
            "url": "https://mcp.example/mcp",
            "headers": {"X-Trace": "keep"},
        }
    ]
    # in-request original untouched
    assert servers[0]["X-API-Key"] == "key-123"
    assert servers[0]["headers"]["x-api-key"] == "lower-key"
    assert servers[0]["headers"]["X-Auth-Token"] == "auth-tok"


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


@pytest.mark.unit
def test_redacting_checkpointer_setup_forwards_to_inner() -> None:
    """``setup()`` is proxied for parity with the wrapped saver (#3969)."""
    calls: list[str] = []

    class _FakeSaverWithSetup:
        def setup(self) -> None:
            calls.append("setup")

    saver = McpTokenRedactingCheckpointer(_FakeSaverWithSetup())
    saver.setup()
    assert calls == ["setup"]


@pytest.mark.unit
def test_redacting_checkpointer_setup_noop_when_inner_lacks_setup() -> None:
    """An inner saver without ``setup`` (e.g. MemorySaver) must not raise."""

    class _FakeSaverNoSetup:
        pass

    saver = McpTokenRedactingCheckpointer(_FakeSaverNoSetup())
    saver.setup()
