"""Redact MCP OAuth/session tokens from durable LangGraph checkpoints (#3794).

``WorkflowState.mcp_servers`` may carry per-turn ``token`` values for Streamable
HTTP MCP calls. Those tokens must stay in-request (graph memory for the active
turn) but must not be written to the checkpointer — checkpoints are archived to
private R2 and would otherwise retain bearer/OAuth access tokens.

Each HTTP turn overwrites ``mcp_servers`` from the BFF header, so resume does
not need persisted tokens.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any  # score:allow untyped any — checkpoint JSON

from langgraph.checkpoint.base import BaseCheckpointSaver

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:  # pragma: no cover - langgraph always pulls this in practice
    RunnableConfig = dict  # type: ignore[misc,assignment]


def redact_mcp_servers_value(value: Any) -> Any:
    """Return *value* with ``token`` keys stripped from mcp_servers entries.

    Non-list values are returned unchanged. Dict entries keep ``id`` / ``url`` /
    ``auth`` (and any other non-secret fields).
    """
    if not isinstance(value, list):
        return value
    redacted: list[Any] = []
    for item in value:
        if isinstance(item, dict) and "token" in item:
            redacted.append({k: v for k, v in item.items() if k != "token"})
        else:
            redacted.append(item)
    return redacted


def redact_checkpoint_mcp_tokens(checkpoint: Mapping[str, Any] | Any) -> Any:
    """Shallow-copy *checkpoint* with ``channel_values.mcp_servers`` tokens removed.

    Does not mutate the caller's checkpoint (in-request state keeps tokens).
    """
    if not isinstance(checkpoint, Mapping):
        return checkpoint
    values = checkpoint.get("channel_values")
    if not isinstance(values, dict) or "mcp_servers" not in values:
        return checkpoint
    new_values = dict(values)
    new_values["mcp_servers"] = redact_mcp_servers_value(values.get("mcp_servers"))
    new_ckpt = dict(checkpoint)
    new_ckpt["channel_values"] = new_values
    return new_ckpt


def redact_checkpoint_writes(writes: Sequence[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """Strip tokens from pending ``mcp_servers`` channel writes."""
    out: list[tuple[str, Any]] = []
    for write in writes:
        if isinstance(write, tuple) and len(write) >= 2 and write[0] == "mcp_servers":
            channel = write[0]
            value = redact_mcp_servers_value(write[1])
            out.append((channel, value, *write[2:]) if len(write) > 2 else (channel, value))
        else:
            out.append(write)
    return out


def unwrap_checkpointer(checkpointer: Any) -> Any:
    """Return the inner saver when *checkpointer* is a redacting wrapper."""
    cur = checkpointer
    while isinstance(cur, McpTokenRedactingCheckpointer):
        cur = cur.inner
    return cur


class McpTokenRedactingCheckpointer(BaseCheckpointSaver):
    """``BaseCheckpointSaver`` that strips ``mcp_servers.token`` on durable writes.

    In-memory / in-request graph state is untouched; only ``put`` / ``put_writes``
    (and async twins) see the redacted payload.
    """

    def __init__(self, inner: BaseCheckpointSaver) -> None:
        super().__init__(serde=getattr(inner, "serde", None))
        self.inner = inner

    @property
    def config_specs(self) -> list:
        return list(getattr(self.inner, "config_specs", []) or [])

    def get_tuple(self, config: RunnableConfig) -> Any:
        return self.inner.get_tuple(config)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[Any]:
        return self.inner.list(config, filter=filter, before=before, limit=limit)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
    ) -> RunnableConfig:
        return self.inner.put(
            config,
            redact_checkpoint_mcp_tokens(checkpoint),
            metadata,
            new_versions,
        )

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.inner.put_writes(
            config,
            redact_checkpoint_writes(writes),
            task_id,
            task_path,
        )

    def delete_thread(self, thread_id: str) -> None:
        return self.inner.delete_thread(thread_id)

    async def aget_tuple(self, config: RunnableConfig) -> Any:
        return await self.inner.aget_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Any:
        async for item in self.inner.alist(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
    ) -> RunnableConfig:
        return await self.inner.aput(
            config,
            redact_checkpoint_mcp_tokens(checkpoint),
            metadata,
            new_versions,
        )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await self.inner.aput_writes(
            config,
            redact_checkpoint_writes(writes),
            task_id,
            task_path,
        )

    async def adelete_thread(self, thread_id: str) -> None:
        return await self.inner.adelete_thread(thread_id)
