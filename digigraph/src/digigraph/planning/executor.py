"""Execute a structured plan: topo-sort by depends_on, resolve placeholders, run layers in parallel."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable


_PLACEHOLDER_PATTERN = re.compile(r"\{\{(\w+)\.(\w+)\}\}")


def _resolve_str(s: str, results: dict[str, Any]) -> str:
    def repl(m: re.Match[str]) -> str:
        sid, key = m.group(1), m.group(2)
        val = results.get(sid)
        if isinstance(val, dict):
            v = val.get(key)
            return str(v) if v is not None else m.group(0)
        return str(val) if val is not None else m.group(0)
    return _PLACEHOLDER_PATTERN.sub(repl, s)


def _resolve_placeholders(args: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    """Replace {{step_id.field}} in string values with results[step_id].get(field)."""
    if not args:
        return dict(args)
    out: dict[str, Any] = {}
    for k, v in args.items():
        if isinstance(v, str):
            out[k] = _resolve_str(v, results)
        elif isinstance(v, dict):
            out[k] = _resolve_placeholders(v, results)
        elif isinstance(v, list):
            new_list: list[Any] = []
            for x in v:
                if isinstance(x, str):
                    new_list.append(_resolve_str(x, results))
                elif isinstance(x, dict):
                    new_list.append(_resolve_placeholders(x, results))
                else:
                    new_list.append(x)
            out[k] = new_list
        else:
            out[k] = v
    return out


def _topo_layers(steps: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Return steps in layers: layer i contains steps whose depends_on are all in earlier layers."""
    step_ids = {s["id"] for s in steps if s.get("id")}
    layers: list[list[dict[str, Any]]] = []
    done: set[str] = set()
    while len(done) < len(step_ids):
        layer: list[dict[str, Any]] = []
        for s in steps:
            sid = s.get("id")
            if not sid or sid in done:
                continue
            deps = s.get("depends_on") or []
            if all(d in done for d in deps):
                layer.append(s)
        if not layer:
            break
        for s in layer:
            done.add(s["id"])
        layers.append(layer)
    return layers


def run_plan(
    steps: list[dict[str, Any]],
    execute_tool: Callable[[str, dict[str, Any]], str | dict[str, Any]],
) -> dict[str, Any]:
    """Execute a plan: topo-sort by depends_on, resolve {{step_id.field}} in args, run each layer in parallel.
    steps: list of { "id": str, "agent": str, "args": dict, "depends_on": list[str]? }.
    Returns dict step_id -> result (str or dict).
    """
    results: dict[str, Any] = {}
    layers = _topo_layers(steps)
    for layer in layers:
        resolved: list[tuple[dict, str, dict]] = []
        for s in layer:
            sid = s.get("id", "")
            agent = s.get("agent", "")
            args = _resolve_placeholders(s.get("args") or {}, results)
            resolved.append((s, agent, args))
        if len(resolved) == 1:
            s, agent, args = resolved[0]
            try:
                out = execute_tool(agent, args)
            except Exception as e:
                out = {"content": str(e)}
            results[s["id"]] = out
        else:
            with ThreadPoolExecutor(max_workers=len(resolved)) as executor:
                future_to_sid = {}
                for s, agent, args in resolved:
                    future_to_sid[executor.submit(execute_tool, agent, args)] = s["id"]
                for future in as_completed(future_to_sid):
                    sid = future_to_sid[future]
                    try:
                        results[sid] = future.result()
                    except Exception as e:
                        results[sid] = {"content": str(e)}
    return results
