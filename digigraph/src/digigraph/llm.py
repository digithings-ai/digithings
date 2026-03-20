"""LLM client: OpenAI-compatible API (Ollama, LiteLLM, OpenAI). Phase 1+."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import logging

import yaml
from openai import OpenAI

logger = logging.getLogger(__name__)

# --- Optional LangSmith tracing ---
# Enabled automatically when LANGSMITH_API_KEY is set and langsmith is installed.
try:
    import langsmith as _langsmith  # type: ignore[import-untyped]
    _LANGSMITH_AVAILABLE = True
except ImportError:
    _langsmith = None  # type: ignore[assignment]
    _LANGSMITH_AVAILABLE = False


def _traceable(name: str):
    """Decorator: wraps a function with LangSmith tracing when available and configured."""
    def decorator(fn):
        if _LANGSMITH_AVAILABLE and os.environ.get("LANGSMITH_API_KEY"):
            try:
                return _langsmith.traceable(name=name)(fn)
            except Exception as exc:
                logger.debug("LangSmith traceable setup failed for %r: %s", name, exc)
        return fn
    return decorator


def _normalize_tool_arguments(args_str: str | None) -> str:
    """Return valid JSON string for tool call arguments. Some models stream invalid JSON (incomplete, trailing comma)."""
    s = (args_str or "").strip()
    if not s:
        return "{}"
    try:
        json.loads(s)
        return s
    except json.JSONDecodeError:
        pass
    # Try common fixes: close unclosed brace, remove trailing comma
    fixed = s.rstrip()
    if fixed and not fixed.endswith("}"):
        if fixed.endswith(","):
            fixed = fixed[:-1] + "}"
        else:
            fixed = fixed + "}"
    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r",\s*}", "}", fixed)
    fixed = re.sub(r",\s*]", "]", fixed)
    try:
        json.loads(fixed)
        return fixed
    except json.JSONDecodeError:
        return "{}"

# Optional: override for Ollama / LiteLLM. Default OpenAI if unset.
_BASE_URL = os.environ.get("OPENAI_API_BASE")
_API_KEY = os.environ.get("OPENAI_API_KEY", "not-set")

# Client cache: (api_key, base_url) -> OpenAI instance.
# Re-uses the underlying httpx connection pool across requests.
# Invalidated automatically when env vars change (cache key includes their values).
_client_cache: dict[tuple[str, str | None], OpenAI] = {}

# LLM response cache: sha256_key -> (response_str, expires_at).
# Only caches non-tool, non-streaming chat_completion calls.
# TTL configurable via DIGI_LLM_CACHE_TTL_SECONDS (default: 3600).
_llm_cache: dict[str, tuple[str, float]] = {}
_LLM_CACHE_MAXSIZE = 256


def _llm_cache_key(model: str, messages: list[dict[str, Any]], temperature: float) -> str:
    """Return a stable SHA-256 cache key for the given completion parameters."""
    payload = json.dumps({"model": model, "messages": messages, "temperature": temperature}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _llm_cache_ttl() -> float:
    try:
        return float(os.environ.get("DIGI_LLM_CACHE_TTL_SECONDS", "3600"))
    except ValueError:
        return 3600.0


def _llm_cache_get(key: str) -> str | None:
    entry = _llm_cache.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        del _llm_cache[key]
        return None
    return value


def _llm_cache_set(key: str, value: str) -> None:
    # Evict oldest entries when at capacity (simple FIFO approximation)
    if len(_llm_cache) >= _LLM_CACHE_MAXSIZE:
        oldest_key = next(iter(_llm_cache))
        del _llm_cache[oldest_key]
    _llm_cache[key] = (value, time.monotonic() + _llm_cache_ttl())

# test = minimal tokens (free tier); medium = balanced; best = largest.
# When DIGI_PROJECT_CONFIG is set, agents.llm_mode overrides DIGI_LLM_MODE.
def _get_llm_mode() -> str:
    """Resolve current LLM mode per request. Always reads env/config fresh to avoid global state."""
    if os.environ.get("DIGI_PROJECT_CONFIG"):
        try:
            from digigraph.project_config import DigiProjectConfig

            cfg = DigiProjectConfig.load()
            mode = cfg.get_llm_mode()
            if mode:
                return mode.lower().strip()
        except Exception as e:
            logger.warning("Failed to load LLM mode from project config: %s", e)
    return os.environ.get("DIGI_LLM_MODE", "test").lower().strip()


def _load_model_modes() -> dict[str, Any]:
    """Load config/model_modes.yaml. Returns {} if missing."""
    config_dir = os.environ.get("DIGI_CONFIG_PATH", "config")
    path = Path(config_dir) / "model_modes.yaml"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Failed to load model_modes.yaml: %s", e)
        return {}


def get_model_for_mode() -> str:
    """
    Return the LiteLLM model name for the current DIGI_LLM_MODE (test|medium|best).
    Reads config/model_modes.yaml defaults; falls back to gpt-4o-mini.
    Mode is resolved per-call so concurrent requests with different DIGI_LLM_MODE are isolated.
    """
    mode = _get_llm_mode()
    data = _load_model_modes()
    defaults = data.get("defaults") or {}
    model = defaults.get(mode) or defaults.get("test")
    if model:
        return model
    return "gpt-4o-mini"


def get_client() -> OpenAI:
    """Return a cached OpenAI client for the current OPENAI_API_KEY / OPENAI_API_BASE values.

    The cache key includes both env var values so the client is recreated automatically
    if either changes at runtime (e.g. in tests). Reusing the client shares its httpx
    connection pool, avoiding per-request TCP handshakes.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "not-set")
    base_url = os.environ.get("OPENAI_API_BASE")
    cache_key = (api_key, base_url)
    client = _client_cache.get(cache_key)
    if client is None:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url.rstrip("/")
        client = OpenAI(**kwargs)
        _client_cache[cache_key] = client
    return client


@_traceable("chat_completion")
def chat_completion(
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] = "auto",
) -> str | tuple[str, list[dict[str, Any]] | None]:
    """
    Chat completion. When tools=None: returns content string (backward compatible).
    When tools provided: returns (content, tool_calls) for tool-calling loop.
    """
    client = get_client()
    effective_model = os.environ.get("OLLAMA_MODEL") or get_model_for_mode() or model
    # Check cache for tool-free requests (tool calls have side effects; don't cache them)
    cache_key: str | None = None
    if not tools:
        cache_key = _llm_cache_key(effective_model, messages, temperature)
        cached = _llm_cache_get(cache_key)
        if cached is not None:
            logger.debug("LLM cache hit: model=%s key=%s…", effective_model, cache_key[:8])
            return cached
    kwargs: dict[str, Any] = {
        "model": effective_model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    r = client.chat.completions.create(**kwargs)
    if not r.choices:
        return "" if not tools else ("", None)
    msg = r.choices[0].message
    content = (msg.content or "").strip()
    tool_calls = getattr(msg, "tool_calls", None)
    if tools and tool_calls:
        tc_list = []
        for tc in tool_calls:
            fn = tc.function
            name = getattr(fn, "name", "") or (fn.get("name", "") if isinstance(fn, dict) else "")
            args = getattr(fn, "arguments", "{}") if not isinstance(fn, dict) else fn.get("arguments", "{}")
            tc_list.append({
                "id": tc.id,
                "type": "function",
                "function": {"name": name, "arguments": args or "{}"},
            })
        return content, tc_list
    if cache_key and content:
        _llm_cache_set(cache_key, content)
    return content


def _stream_completion_one_turn(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] = "auto",
    on_content_delta: Callable[[str], None] | None = None,
    on_reasoning_delta: Callable[[str], None] | None = None,
) -> tuple[str, list[dict[str, Any]] | None]:
    """
    One completion with stream=True. Accumulates content and tool_calls; calls on_content_delta(delta)
    for each content chunk and on_reasoning_delta(delta) for each reasoning_content chunk when present.
    Returns (content, tool_calls or None). When tool_calls is not None, caller should run tools and loop.
    """
    effective_model = os.environ.get("OLLAMA_MODEL") or get_model_for_mode() or model
    kwargs: dict[str, Any] = {
        "model": effective_model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    stream = client.chat.completions.create(**kwargs)
    content_parts: list[str] = []
    tool_calls_accum: dict[int, dict[str, Any]] = {}  # index -> {id, type, function: {name, arguments}}

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if not delta:
            continue
        try:
            reasoning_piece = getattr(delta, "reasoning_content", None)
            if reasoning_piece is not None and on_reasoning_delta:
                on_reasoning_delta(str(reasoning_piece) if reasoning_piece else "")
        except Exception as e:
            logger.debug("Failed to process reasoning_content delta: %s", e)
        if getattr(delta, "content", None):
            piece = delta.content or ""
            accumulated = "".join(content_parts)
            content_parts.append(piece)
            # Some providers send the full message again in the last chunk; only emit the new part to avoid duplicate
            if on_content_delta and piece:
                if accumulated and piece.startswith(accumulated) and len(piece) > len(accumulated):
                    piece = piece[len(accumulated):]
                elif accumulated and piece == accumulated:
                    piece = ""
                if piece:
                    on_content_delta(piece)
        tool_calls = getattr(delta, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                idx = getattr(tc, "index", None)
                if idx is None:
                    continue
                if idx not in tool_calls_accum:
                    tool_calls_accum[idx] = {
                        "id": getattr(tc, "id", "") or "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                acc = tool_calls_accum[idx]
                if getattr(tc, "id", None):
                    acc["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn:
                    if getattr(fn, "name", None):
                        acc["function"]["name"] = (acc["function"]["name"] or "") + (fn.name or "")
                    if getattr(fn, "arguments", None):
                        acc["function"]["arguments"] = (acc["function"]["arguments"] or "") + (fn.arguments or "")

    content = "".join(content_parts).strip()
    if tool_calls_accum:
        indices = sorted(tool_calls_accum.keys())
        tc_list = []
        for i in indices:
            acc = tool_calls_accum[i]
            args_raw = acc["function"].get("arguments", "{}")
            tc_list.append({
                "id": acc["id"],
                "type": acc["type"],
                "function": {
                    "name": acc["function"]["name"],
                    "arguments": _normalize_tool_arguments(args_raw),
                },
            })
        return content, tc_list
    return content, None


@_traceable("chat_completion_with_tools")
def chat_completion_with_tools(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    execute_tool: "typing.Callable[[str, dict[str, Any]], str]",
    *,
    temperature: float = 0.2,
    max_tool_rounds: int = 5,
    on_tool_step: Callable[[str, dict[str, Any]], None] | None = None,
) -> str:
    """
    Run a tool-calling loop until the model returns a final response.
    execute_tool(name: str, arguments: dict) -> str.
    When on_tool_step is set, calls it with ("tool_call", {name, arguments}) before
    execute_tool and ("tool_result", {content: result}) after. When streaming, emits
    ("content", delta) for each token of the final answer and ("reasoning", delta) for
    each reasoning_content chunk when the model provides it (e.g. reasoning/thinking models).
    """
    client = get_client()
    current = list(messages)
    content = ""
    use_streaming = on_tool_step is not None

    def do_one_turn():
        if use_streaming:
            def on_delta(delta: str) -> None:
                if on_tool_step and delta:
                    on_tool_step("content", delta)

            def on_reasoning(delta: str) -> None:
                if on_tool_step and delta:
                    on_tool_step("reasoning", delta)

            return _stream_completion_one_turn(
                client,
                model,
                current,
                temperature=temperature,
                tools=tools,
                tool_choice="auto",
                on_content_delta=on_delta,
                on_reasoning_delta=on_reasoning,
            )
        out = chat_completion(
            model, current, temperature=temperature, tools=tools, tool_choice="auto"
        )
        if isinstance(out, tuple):
            return out
        return (out or "", None)

    for _ in range(max_tool_rounds):
        out = do_one_turn()
        if isinstance(out, tuple):
            content, tool_calls = out
        else:
            return (out or "") if isinstance(out, str) else ""
        if not tool_calls:
            return content or ""
        asst_entries = []
        for tc in tool_calls:
            fn = tc.get("function") if isinstance(tc, dict) else {}
            if isinstance(fn, dict):
                name = fn.get("name", "")
                args_str = fn.get("arguments", "{}")
            else:
                name = getattr(fn, "name", "") if fn else ""
                args_str = getattr(fn, "arguments", "{}") if fn else "{}"
            asst_entries.append({
                "id": tc.get("id", ""),
                "type": "function",
                "function": {"name": name, "arguments": _normalize_tool_arguments(args_str)},
            })
        asst: dict[str, Any] = {"role": "assistant", "content": content or None, "tool_calls": asst_entries}
        current.append(asst)
        # Parse (tc, name, args) for each tool call
        parsed: list[tuple[dict, str, dict]] = []
        for tc in tool_calls:
            fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
            if isinstance(fn, dict):
                name = fn.get("name", "")
                args_str = fn.get("arguments", "{}")
            else:
                name = getattr(fn, "name", "") if fn else ""
                args_str = getattr(fn, "arguments", "{}") if fn else "{}"
            args_str = _normalize_tool_arguments(args_str if isinstance(args_str, str) else str(args_str))
            try:
                args = json.loads(args_str)
            except Exception as e:
                logger.warning("Failed to parse tool arguments as JSON (name=%s): %s — using {}", name, e)
                args = {}
            parsed.append((tc, name, args))
        # Run in parallel only when all calls are delegate/parallel_safe tools
        try:
            from digigraph.orchestration.registry import list_tool_names
            parallel_safe = set(list_tool_names("parallel_safe"))
        except Exception as e:
            logger.debug("Could not load parallel_safe tool list: %s", e)
            parallel_safe = set()
        all_parallel_safe = (
            len(parsed) > 1
            and all(name in parallel_safe for (_, name, _) in parsed)
        )
        if all_parallel_safe:
            with ThreadPoolExecutor(max_workers=len(parsed)) as executor:
                future_to_idx = {
                    executor.submit(execute_tool, name, args): i
                    for i, (_, name, args) in enumerate(parsed)
                }
                results: dict[int, str | dict[str, Any]] = {}
                for future in as_completed(future_to_idx):
                    i = future_to_idx[future]
                    try:
                        results[i] = future.result()
                    except Exception as e:
                        results[i] = {"content": str(e)}
            for i, (tc, name, args) in enumerate(parsed):
                result = results[i]
                if on_tool_step is not None:
                    on_tool_step("tool_call", {"name": name, "arguments": args})
                    payload = {"name": name, **(result if isinstance(result, dict) else {"content": result})}
                    on_tool_step("tool_result", payload)
                msg_content = result.get("content", str(result)) if isinstance(result, dict) else str(result)
                current.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": msg_content}
                )
        else:
            for tc, name, args in parsed:
                if on_tool_step is not None:
                    on_tool_step("tool_call", {"name": name, "arguments": args})
                result = execute_tool(name, args)
                if on_tool_step is not None:
                    payload = {"name": name, **(result if isinstance(result, dict) else {"content": result})}
                    on_tool_step("tool_result", payload)
                msg_content = result.get("content", str(result)) if isinstance(result, dict) else str(result)
                current.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": msg_content}
                )
    # Hit max rounds with no final content: force one more call without tools
    if not content and len(current) > len(messages):
        current.append(
            {"role": "user", "content": "Based on the search results above, provide a concise summary for the user."}
        )
        if use_streaming:
            def on_delta(delta: str) -> None:
                if on_tool_step and delta:
                    on_tool_step("content", delta)

            def on_reasoning(delta: str) -> None:
                if on_tool_step and delta:
                    on_tool_step("reasoning", delta)

            out, _ = _stream_completion_one_turn(
                client,
                model,
                current,
                temperature=temperature,
                on_content_delta=on_delta,
                on_reasoning_delta=on_reasoning,
            )
            return (out or "") or ""
        out = chat_completion(model, current, temperature=temperature)
        return (out if isinstance(out, str) else "") or ""
    return content or ""
