"""Redact MCP OAuth/session secrets from durable LangGraph checkpoints (#3794, #3969).

``WorkflowState.mcp_servers`` may carry per-turn ``token`` values for Streamable
HTTP MCP calls. Those tokens must stay in-request (graph memory for the active
turn) but must not be written to the checkpointer — checkpoints are archived to
private R2 and would otherwise retain bearer/OAuth access tokens.

Redaction is a recursive secret-key denylist (#3969), not a single ``token``
match, so a future secret-bearing field (``authorization``, ``api_key``,
``client_secret``, a nested ``headers`` / ``auth`` sub-object, …) cannot persist
either. Non-secret fields (``id`` / ``url`` / a scheme string ``auth``) survive.

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

# Exact (case-insensitive) secret field names, plus suffix heuristics so a future
# ``*_token`` / ``*_secret`` / ``*_password`` field is caught without a code change.
_SECRET_KEY_NAMES = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "auth_token",
        "session_token",
        "authorization",
        "api_key",
        "apikey",
        "client_secret",
        "secret",
        "password",
        "passwd",
        "private_key",
        "bearer",
    }
)
_SECRET_KEY_SUFFIXES = ("_token", "_secret", "_password", "_api_key")


def _is_secret_key(key: str) -> bool:
    # Normalize wire-style hyphenated header names (`X-API-Key`) to the
    # underscore form the denylist is written in (`api_key`).
    normalized = key.strip().lower().replace("-", "_")
    return normalized in _SECRET_KEY_NAMES or normalized.endswith(_SECRET_KEY_SUFFIXES)


def _redact_secrets(value: Any) -> Any:
    """Recursively drop secret-named dict keys; lists are walked, scalars pass through."""
    if isinstance(value, Mapping):
        return {
            key: _redact_secrets(item)
            for key, item in value.items()
            if not (isinstance(key, str) and _is_secret_key(key))
        }
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def redact_mcp_servers_value(value: Any) -> Any:
    """Return *value* with secret-named keys stripped from mcp_servers entries.

    Non-list values are returned unchanged. Dict entries keep ``id`` / ``url`` /
    ``auth`` (and any other non-secret fields); secret keys are removed recursively
    through nested sub-objects (#3969). The input is not mutated.
    """
    if not isinstance(value, list):
        return value
    return [_redact_secrets(item) for item in value]


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
    """``BaseCheckpointSaver`` that strips ``mcp_servers`` secrets on durable writes.

    In-memory / in-request graph state is untouched; only ``put`` / ``put_writes``
    (and async twins) see the redacted payload. ``setup()`` is proxied to the inner
    saver so the wrapper stays transparent for schema/DDL bootstrap.
    """

    def __init__(self, inner: BaseCheckpointSaver) -> None:
        super().__init__(serde=getattr(inner, "serde", None))
        self.inner = inner

    def setup(self) -> None:
        """Forward ``setup()`` to the inner saver when it defines one.

        Production calls ``setup()`` on the inner saver *before* wrapping
        (``graph.py``); proxying keeps the wrapper transparent for any caller that
        legitimately needs it. ``MemorySaver`` has no ``setup`` — that is a no-op.
        """
        inner_setup = getattr(self.inner, "setup", None)
        if callable(inner_setup):
            inner_setup()

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
