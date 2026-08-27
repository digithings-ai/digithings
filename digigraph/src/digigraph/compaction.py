"""Two-tier context compaction for long-running research sessions (#399).

Non-destructive: compaction changes the **LLM view** of messages. Originals are
offloaded to the session workspace; LangGraph checkpoint message records are not
rewritten. Callers store the returned :class:`CompactionEvent` on graph state as
``_compaction_event`` and feed ``llm_messages`` to digillm.

Tier 1 — Truncation: for messages outside the most recent
``keep_recent_messages``, tool-result payloads larger than
``tier1_truncation_kb`` are written to ``workspace/tool_results/msg_<id>.json``
and replaced with a short reference stub.

Tier 2 — Summarisation: when estimated tokens exceed ``token_threshold``, the
oldest messages (keeping the recent window intact) are summarised via
``summary_model`` (default ``digi/fast``) and replaced by a tagged HumanMessage
so future passes do not re-summarise the summary.
"""

from __future__ import annotations

import json
import logging
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any  # score:allow untyped any — OpenAI-style message dicts / tool payloads

from pydantic import BaseModel, Field

from digigraph.run_storage import _sanitize_session_id, get_run_data_dir

logger = logging.getLogger(__name__)

# Tag embedded in the injected summary HumanMessage. Tier-2 eviction skips any
# message whose content contains this marker so summaries are not re-summarised.
COMPACTION_SUMMARY_TAG = "[COMPACTION_SUMMARY]"

# Reference stub left in place of a truncated tool payload (tier 1).
_TRUNCATION_STUB_TMPL = "[truncated — full result in workspace/tool_results/{filename}]"


class CompactionConfig(BaseModel):
    """Knobs for two-tier context compaction (#399)."""

    enabled: bool = True
    token_threshold: int = 80_000
    keep_recent_messages: int = 10
    tier1_truncation_kb: int = 2
    summary_model: str = "digi/fast"


class CompactionEvent(BaseModel):
    """Lean record of one compaction pass — stored on WorkflowState as ``_compaction_event``."""

    event_id: str
    tier1_truncated: int = 0
    tier1_refs: list[str] = Field(default_factory=list)
    tier2_triggered: bool = False
    tier2_evicted_count: int = 0
    tier2_evicted_ref: str | None = None
    tokens_before: int = 0
    tokens_after: int = 0
    summary_tag: str = COMPACTION_SUMMARY_TAG


class CompactionResult(BaseModel):
    """LLM-facing messages plus the non-destructive compaction event."""

    llm_messages: list[dict[str, Any]]
    event: CompactionEvent | None = None
    # Deep copy of the input messages before any mutation — callers that checkpoint
    # original transcripts can persist this (or rely on workspace refs) without
    # depending on the compacted LLM view.
    original_messages: list[dict[str, Any]] = Field(default_factory=list)


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Approximate token count (chars/4), matching digigraph.chat_prompt soft budgets."""
    total_chars = 0
    for msg in messages:
        content = msg.get("content")
        if content is None:
            continue
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    total_chars += len(part["text"])
                else:
                    total_chars += len(str(part))
        else:
            total_chars += len(str(content))
        # Cheap accounting for tool_calls argument blobs when present.
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            total_chars += len(json.dumps(tool_calls, default=str))
    return max(0, total_chars // 4)


def _message_content_str(msg: dict[str, Any]) -> str:
    content = msg.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
            else:
                parts.append(str(part))
        return "\n".join(parts)
    return str(content)


def _is_summary_message(msg: dict[str, Any]) -> bool:
    return COMPACTION_SUMMARY_TAG in _message_content_str(msg)


def _is_tool_result(msg: dict[str, Any]) -> bool:
    role = (msg.get("role") or "").strip().lower()
    return role == "tool"


def _msg_id(msg: dict[str, Any], index: int) -> str:
    for key in ("tool_call_id", "id", "name"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in val.strip())
            return safe[:64] or f"idx_{index}"
    return f"idx_{index}"


def session_workspace_dir(session_id: str | None) -> Path | None:
    """Return ``{run_data_dir}/{session}/workspace`` when run_data_dir is configured."""
    root = get_run_data_dir()
    if not root:
        return None
    safe = _sanitize_session_id(session_id)
    return Path(root).resolve() / safe / "workspace"


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=str, ensure_ascii=False), encoding="utf-8")
    return str(path.resolve())


def offload_tool_result(
    session_id: str | None,
    msg_id: str,
    content: str,
    *,
    workspace: Path | None = None,
) -> str | None:
    """Write a tool payload to ``workspace/tool_results/msg_<id>.json``. Return path or None."""
    base = workspace if workspace is not None else session_workspace_dir(session_id)
    if base is None:
        return None
    filename = f"msg_{msg_id}.json"
    path = base / "tool_results" / filename
    try:
        return _write_json(path, {"msg_id": msg_id, "content": content})
    except OSError as exc:
        logger.warning("compaction: failed to offload tool result %s: %s", msg_id, exc)
        return None


def offload_evicted_messages(
    session_id: str | None,
    messages: list[dict[str, Any]],
    *,
    event_id: str,
    workspace: Path | None = None,
) -> str | None:
    """Write evicted messages to ``workspace/compaction/evicted_<event_id>.json``."""
    base = workspace if workspace is not None else session_workspace_dir(session_id)
    if base is None:
        return None
    path = base / "compaction" / f"evicted_{event_id}.json"
    try:
        return _write_json(path, {"event_id": event_id, "messages": messages})
    except OSError as exc:
        logger.warning("compaction: failed to offload evicted messages: %s", exc)
        return None


def load_workspace_json(ref: str) -> Any:
    """Load a previously offloaded JSON blob by absolute path (resume / data-loss checks)."""
    path = Path(ref).resolve()
    return json.loads(path.read_text(encoding="utf-8"))


def apply_tier1_truncation(
    messages: list[dict[str, Any]],
    config: CompactionConfig,
    *,
    session_id: str | None = None,
    workspace: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Truncate large tool results outside the recent window; offload originals.

    Returns ``(llm_view, workspace_refs)``. Messages already carrying a truncation
    stub are left alone. Non-tool messages are never truncated by tier 1.
    """
    if not messages:
        return messages, []
    keep = max(0, config.keep_recent_messages)
    threshold_bytes = max(1, config.tier1_truncation_kb) * 1024
    # Indices eligible for truncation: everything before the recent window.
    cutoff = max(0, len(messages) - keep) if keep else len(messages)
    out = deepcopy(messages)
    refs: list[str] = []
    for i in range(cutoff):
        msg = out[i]
        if not _is_tool_result(msg):
            continue
        content = _message_content_str(msg)
        if not content or content.startswith("[truncated — full result in workspace/"):
            continue
        if len(content.encode("utf-8")) <= threshold_bytes:
            continue
        msg_id = _msg_id(msg, i)
        filename = f"msg_{msg_id}.json"
        ref = offload_tool_result(session_id, msg_id, content, workspace=workspace)
        if ref:
            refs.append(ref)
        stub = _TRUNCATION_STUB_TMPL.format(filename=filename)
        out[i] = {**msg, "content": stub}
    return out, refs


def _format_messages_for_summary(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for msg in messages:
        role = (msg.get("role") or "unknown").strip()
        body = _message_content_str(msg)
        if len(body) > 4000:
            body = body[:4000] + "…"
        lines.append(f"[{role}] {body}")
    return "\n\n".join(lines)


def summarise_messages(
    messages: list[dict[str, Any]],
    *,
    model: str,
) -> str:
    """Summarise *messages* with ``model`` via digigraph.llm_client.completion_text."""
    from digigraph.llm_client import completion_text

    prompt = (
        "Summarise the following conversation excerpt for a continuing research session. "
        "Preserve key facts, numbers, dataset_refs, tickers, decisions, and open questions. "
        "Omit boilerplate and repeated tool noise. Output plain prose, no markdown fences.\n\n"
        + _format_messages_for_summary(messages)
    )
    text = completion_text(
        model,
        [
            {
                "role": "system",
                "content": "You compress research-session context. Be dense and factual.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=2048,
    )
    return (text or "").strip() or "(empty compaction summary)"


def apply_tier2_summarisation(
    messages: list[dict[str, Any]],
    config: CompactionConfig,
    *,
    session_id: str | None = None,
    workspace: Path | None = None,
    event_id: str | None = None,
    summarise: Any | None = None,
) -> tuple[list[dict[str, Any]], int, str | None]:
    """Evict oldest messages over the token threshold; inject a tagged summary.

    Returns ``(llm_view, evicted_count, evicted_ref)``. Summary messages already
    tagged with :data:`COMPACTION_SUMMARY_TAG` are never included in the eviction
    set (they stay or move with the kept prefix as protected).
    """
    tokens = estimate_tokens(messages)
    if tokens <= config.token_threshold:
        return messages, 0, None

    keep = max(0, config.keep_recent_messages)
    if keep >= len(messages):
        return messages, 0, None

    recent = messages[-keep:] if keep else []
    older = messages[:-keep] if keep else list(messages)
    # Protect prior summaries: keep them immediately before the recent window
    # rather than feeding them back into the summariser.
    protected = [m for m in older if _is_summary_message(m)]
    to_evict = [m for m in older if not _is_summary_message(m)]
    if not to_evict:
        return messages, 0, None

    eid = event_id or uuid.uuid4().hex[:12]
    evicted_ref = offload_evicted_messages(session_id, to_evict, event_id=eid, workspace=workspace)

    summarise_fn = summarise or summarise_messages
    summary_body = summarise_fn(to_evict, model=config.summary_model)
    summary_msg: dict[str, Any] = {
        "role": "user",
        "content": (
            f"{COMPACTION_SUMMARY_TAG} Prior context was compacted to stay under the "
            f"token budget. Full evicted messages: "
            f"{evicted_ref or 'workspace/compaction (unavailable)'}.\n\n{summary_body}"
        ),
    }
    out = [*protected, summary_msg, *recent]
    return out, len(to_evict), evicted_ref


def compact_messages(
    messages: list[dict[str, Any]],
    config: CompactionConfig | None = None,
    *,
    session_id: str | None = None,
    workspace: Path | None = None,
    summarise: Any | None = None,
) -> CompactionResult:
    """Apply tier-1 then tier-2 compaction. Returns LLM view + optional event.

    When ``config.enabled`` is False, returns a deep-copied message list and no event.
    Originals are always preserved on :attr:`CompactionResult.original_messages` and,
    when a workspace is available, on disk under ``tool_results/`` / ``compaction/``.
    """
    cfg = config or CompactionConfig()
    originals = deepcopy(messages)
    if not cfg.enabled or not messages:
        return CompactionResult(llm_messages=deepcopy(messages), original_messages=originals)

    tokens_before = estimate_tokens(messages)
    event_id = uuid.uuid4().hex[:12]
    ws = workspace if workspace is not None else session_workspace_dir(session_id)

    view, tier1_refs = apply_tier1_truncation(messages, cfg, session_id=session_id, workspace=ws)
    view, evicted_count, evicted_ref = apply_tier2_summarisation(
        view,
        cfg,
        session_id=session_id,
        workspace=ws,
        event_id=event_id,
        summarise=summarise,
    )
    tokens_after = estimate_tokens(view)

    changed = bool(tier1_refs) or evicted_count > 0
    if not changed:
        # Still emit an event when we *would* have triggered tier-2 by token count
        # but had nothing to evict (e.g. all older msgs were already summaries) —
        # only skip the event when neither tier mutated the view.
        if tokens_before <= cfg.token_threshold:
            return CompactionResult(llm_messages=view, original_messages=originals)

    event = CompactionEvent(
        event_id=event_id,
        tier1_truncated=len(tier1_refs),
        tier1_refs=tier1_refs,
        tier2_triggered=evicted_count > 0 or tokens_before > cfg.token_threshold,
        tier2_evicted_count=evicted_count,
        tier2_evicted_ref=evicted_ref,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
    )
    return CompactionResult(llm_messages=view, event=event, original_messages=originals)


def compaction_config_from_env() -> CompactionConfig:
    """Build :class:`CompactionConfig` with optional ``DIGI_COMPACTION_*`` overrides."""
    import os

    def _bool(name: str, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None or not str(raw).strip():
            return default
        return str(raw).strip().lower() in ("1", "true", "yes", "on")

    def _int(name: str, default: int) -> int:
        raw = os.environ.get(name)
        if raw is None or not str(raw).strip():
            return default
        try:
            return int(str(raw).strip())
        except ValueError:
            logger.warning("Invalid %s=%r; using default %d", name, raw, default)
            return default

    model = (os.environ.get("DIGI_COMPACTION_SUMMARY_MODEL") or "").strip() or "digi/fast"
    return CompactionConfig(
        enabled=_bool("DIGI_COMPACTION_ENABLED", True),
        token_threshold=_int("DIGI_COMPACTION_TOKEN_THRESHOLD", 80_000),
        keep_recent_messages=_int("DIGI_COMPACTION_KEEP_RECENT", 10),
        tier1_truncation_kb=_int("DIGI_COMPACTION_TIER1_KB", 2),
        summary_model=model,
    )


def maybe_truncate_tool_payload(
    content: str,
    *,
    config: CompactionConfig | None = None,
    session_id: str | None = None,
    msg_id: str | None = None,
    workspace: Path | None = None,
) -> tuple[str, str | None]:
    """Tier-1 truncate a single tool payload for inject-time wrapping.

    Used by :func:`wrap_execute_tool_for_tier1` so large results are offloaded
    *before* digillm appends them to its local transcript (digigraph-scoped;
    digillm's own char cap still applies afterward).
    """
    cfg = config or compaction_config_from_env()
    if not cfg.enabled or not content:
        return content, None
    threshold_bytes = max(1, cfg.tier1_truncation_kb) * 1024
    if len(content.encode("utf-8")) <= threshold_bytes:
        return content, None
    if content.startswith("[truncated — full result in workspace/"):
        return content, None
    mid = msg_id or uuid.uuid4().hex[:12]
    filename = f"msg_{mid}.json"
    ref = offload_tool_result(session_id, mid, content, workspace=workspace)
    stub = _TRUNCATION_STUB_TMPL.format(filename=filename)
    return stub, ref


def wrap_execute_tool_for_tier1(
    execute_tool: Any,
    *,
    config: CompactionConfig | None = None,
    session_id: str | None = None,
    workspace: Path | None = None,
    refs_out: list[str] | None = None,
) -> Any:
    """Wrap an ``execute_tool(name, args)`` so large string/dict ``content`` is tier-1 truncated."""
    cfg = config or compaction_config_from_env()
    if not cfg.enabled:
        return execute_tool

    def _wrapped(name: str, args: dict[str, Any]) -> str | dict[str, Any]:
        result = execute_tool(name, args)
        if isinstance(result, dict):
            raw = result.get("content", "")
            if not isinstance(raw, str):
                raw = str(raw)
            stub, ref = maybe_truncate_tool_payload(
                raw,
                config=cfg,
                session_id=session_id,
                msg_id=f"{name}_{uuid.uuid4().hex[:8]}",
                workspace=workspace,
            )
            if ref and refs_out is not None:
                refs_out.append(ref)
            if stub is not raw:
                return {**result, "content": stub}
            return result
        if isinstance(result, str):
            stub, ref = maybe_truncate_tool_payload(
                result,
                config=cfg,
                session_id=session_id,
                msg_id=f"{name}_{uuid.uuid4().hex[:8]}",
                workspace=workspace,
            )
            if ref and refs_out is not None:
                refs_out.append(ref)
            return stub
        return result

    return _wrapped
