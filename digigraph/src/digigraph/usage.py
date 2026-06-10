"""Thread-safe per-run LLM/search usage accumulator (#663).

A process-global, opt-in sink: ``start()`` activates capture for a run, the LLM
helpers (``chat_completion`` / ``web_search`` / ``x_search``) call ``record(...)``,
and the pipeline reads ``snapshot()`` at run end to write a diagnostics row.
No-op until ``start()`` so library callers pay nothing. Phases may fan out across
threads, so all mutation is under a lock.
"""

from __future__ import annotations

import threading
from typing import Any  # noqa  # scored-lint suppression: heterogeneous call records

_LOCK = threading.Lock()
_ACTIVE = False
_CALLS: list[dict[str, Any]] = []

_SEARCH_KINDS = {"web_search", "x_search"}


def start() -> None:
    """Activate capture and clear any prior calls."""
    global _ACTIVE
    with _LOCK:
        _ACTIVE = True
        _CALLS.clear()


def reset() -> None:
    """Deactivate capture and clear."""
    global _ACTIVE
    with _LOCK:
        _ACTIVE = False
        _CALLS.clear()


def is_active() -> bool:
    return _ACTIVE


def record(
    *,
    kind: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    sources: int = 0,
    ok: bool = True,
) -> None:
    """Record one LLM/search call. No-op unless capture is active."""
    if not _ACTIVE:
        return
    with _LOCK:
        _CALLS.append(
            {
                "kind": kind,
                "model": model,
                "prompt_tokens": int(prompt_tokens or 0),
                "completion_tokens": int(completion_tokens or 0),
                "sources": int(sources or 0),
                "ok": bool(ok),
            }
        )


def snapshot() -> dict[str, Any]:
    """Aggregate the recorded calls into run-level totals + a per-kind breakdown."""
    with _LOCK:
        calls = list(_CALLS)
    chat = [c for c in calls if c["kind"] == "chat"]
    search = [c for c in calls if c["kind"] in _SEARCH_KINDS]
    prompt = sum(c["prompt_tokens"] for c in chat)
    completion = sum(c["completion_tokens"] for c in chat)
    by_kind: dict[str, dict[str, int]] = {}
    for c in calls:
        b = by_kind.setdefault(
            c["kind"], {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "sources": 0}
        )
        b["calls"] += 1
        b["prompt_tokens"] += c["prompt_tokens"]
        b["completion_tokens"] += c["completion_tokens"]
        b["sources"] += c["sources"]
    return {
        "llm_calls": len(chat),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "search_calls": len(search),
        "sources_used": sum(c["sources"] for c in search),
        "grounding_ok": sum(1 for c in search if c["ok"]),
        "grounding_failed": sum(1 for c in search if not c["ok"]),
        "models": sorted({c["model"] for c in calls}),
        "by_kind": by_kind,
    }
