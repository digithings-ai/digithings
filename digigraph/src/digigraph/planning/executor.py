"""Execute a structured plan: topo-sort by depends_on, resolve placeholders, run layers in parallel."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from typing import Any, Callable

_PLACEHOLDER_PATTERN = re.compile(r"\{\{(\w+)\.(\w+)\}\}")

_PLAN_STEP_ERRORS = (
    ValueError,
    OSError,
    RuntimeError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
)


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


def _run_step(
    execute_tool: Callable[[str, dict[str, Any]], str | dict[str, Any]],
    agent: str,
    args: dict[str, Any],
) -> str | dict[str, Any]:
    try:
        return execute_tool(agent, args)
    except _PLAN_STEP_ERRORS as e:
        return {"content": str(e)}


def _run_step_in_fan_out(
    execute_tool: Callable[[str, dict[str, Any]], str | dict[str, Any]],
    agent: str,
    args: dict[str, Any],
) -> str | dict[str, Any]:
    """Run one layer step in a pool worker: credentials inherited, telemetry handles dropped.

    Both logical-call layers have to be dropped, not just digillm's: digigraph's
    ``usage._LOGICAL_CALL_CONTEXT`` holds the same mutable handle one layer up, so leaving
    it bound would put every step in the layer back on one shared handle. digillm's own
    fan-out runs the second clear through a registered hook; this pool copies the context
    itself, so it calls both directly.
    """
    # Local imports so this module stays importable without the LLM stack, as it was
    # before it had any reason to reach into digillm at all. ``digigraph.usage`` imports
    # digillm itself, so it is the same weight.
    #
    # Guarded because these run *outside* ``_run_step``'s handler, which already counts
    # ``ImportError`` as a one-step failure (see ``_PLAN_STEP_ERRORS``). An unguarded
    # raise here escapes the worker instead, and ``run_plan``'s bare ``future.result()``
    # would discard every *other* step in the layer -- where the serial branch would
    # have degraded to one error string. Nothing is lost by skipping the detach: the
    # modules that bind these handles are the ones that failed to import, so there is
    # no bound handle left to share. A detach that *itself* raises stays loud.
    try:
        from digillm import detach_provider_call_context

        from digigraph.usage import detach_logical_call_context
    except ImportError:
        pass
    else:
        detach_provider_call_context()
        detach_logical_call_context()
    return _run_step(execute_tool, agent, args)


def run_plan(
    steps: list[dict[str, Any]],
    execute_tool: Callable[[str, dict[str, Any]], str | dict[str, Any]],
) -> dict[str, Any]:
    """Execute a plan: topo-sort by depends_on, resolve {{step_id.field}} in args, run each layer in parallel."""
    results: dict[str, Any] = {}
    layers = _topo_layers(steps)
    for layer in layers:
        resolved: list[tuple[dict, str, dict]] = []
        for s in layer:
            agent = s.get("agent", "")
            args = _resolve_placeholders(s.get("args") or {}, results)
            resolved.append((s, agent, args))
        if len(resolved) == 1:
            s, agent, args = resolved[0]
            results[s["id"]] = _run_step(execute_tool, agent, args)
            continue
        # Each step runs inside a copy of *this* context: a pool worker starts with an
        # empty one, so a step that reaches an LLM (the delegate agents are exactly that)
        # would lose the per-request BYOK binding and spend the operator's key. A fresh
        # copy per submit -- one shared Context cannot be entered by two threads at once.
        #
        # A copy propagates references, so it would also hand every step in the layer the
        # same mutable logical-call telemetry handle to race -- in *both* the digillm and
        # the digigraph logical-call var, which carry the same handle. Propagate
        # credentials, not the handle -- hence ``_run_step_in_fan_out``, which the serial
        # branch above deliberately does not use: it runs in this context, not a copy of
        # it, and unbinding the caller's own handle would lose its deferred records.
        with ThreadPoolExecutor(max_workers=len(resolved)) as executor:
            future_to_sid = {
                executor.submit(
                    copy_context().run, _run_step_in_fan_out, execute_tool, agent, args
                ): s["id"]
                for s, agent, args in resolved
            }
            for future in as_completed(future_to_sid):
                results[future_to_sid[future]] = future.result()
    return results
