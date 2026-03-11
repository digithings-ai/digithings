"""LLM client: OpenAI-compatible API (Ollama, LiteLLM, OpenAI). Phase 1+."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

import yaml
from openai import OpenAI


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

# test = minimal tokens (free tier); medium = balanced; best = largest.
# When DIGI_PROJECT_CONFIG is set, agents.llm_mode overrides DIGI_LLM_MODE.
def _get_llm_mode() -> str:
    if os.environ.get("DIGI_PROJECT_CONFIG"):
        try:
            from digigraph.project_config import DigiProjectConfig

            cfg = DigiProjectConfig.load()
            mode = cfg.get_llm_mode()
            if mode:
                return mode.lower().strip()
        except Exception:
            pass
    return os.environ.get("DIGI_LLM_MODE", "test").lower().strip()


_DIGI_LLM_MODE = _get_llm_mode()


def _load_model_modes() -> dict[str, Any]:
    """Load config/model_modes.yaml. Returns {} if missing."""
    config_dir = os.environ.get("DIGI_CONFIG_PATH", "config")
    path = Path(config_dir) / "model_modes.yaml"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_model_for_mode() -> str:
    """
    Return the LiteLLM model name for the current DIGI_LLM_MODE (test|medium|best).
    Reads config/model_modes.yaml defaults; falls back to gpt-4o-mini.
    """
    data = _load_model_modes()
    defaults = data.get("defaults") or {}
    model = defaults.get(_DIGI_LLM_MODE) or defaults.get("test")
    if model:
        return model
    return "gpt-4o-mini"


def get_client() -> OpenAI:
    """Build OpenAI client; uses OPENAI_API_BASE for Ollama/LiteLLM."""
    kwargs: dict[str, Any] = {"api_key": _API_KEY}
    if _BASE_URL:
        kwargs["base_url"] = _BASE_URL.rstrip("/")
    return OpenAI(**kwargs)


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
        except Exception:
            pass
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
            except Exception:
                args = {}
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
