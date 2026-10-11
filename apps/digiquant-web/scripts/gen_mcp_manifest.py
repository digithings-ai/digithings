#!/usr/bin/env python3
"""Generate ``apps/digiquant-web/app/_mcp-tools.json`` from the digiquant MCP server.

The manifest is the tool list the digiquant.io surface advertises, so it must be
true twice over: every tool in it must be **registered** on the server, and every
tool in it must have **returned a real answer** when called. This script holds
both halves.

Registration (``routed()``) is read out of the same source the server registers
from, with ``ast`` only — no imports, no ``mcp`` install — so the two cannot
drift the way a hand-written list does. It mirrors ``_maybe_tool`` in
``digiquant/src/digiquant/mcp_server.py``: a name is registered when it is not
refused by :mod:`digiquant.tool_refusals` and its declared entitlement is not
one of the ``session``/``preview``/``pro`` tools that need the deployer's own
Gloomberb cookie.

Audited behaviour (``AUDITED_KEEP``) is empirical and dated: the 2026-10-11 audit
called every registered tool against the local stack and kept the ones that
answered. A tool that is registered but is not in ``AUDITED_KEEP`` is dropped,
because showing it would over-claim. Re-run the audit and extend ``AUDITED_KEEP``
when the environment changes — see the runbook note at the bottom of this file.

Usage::

    python scripts/gen_mcp_manifest.py            # rewrite the manifest
    python scripts/gen_mcp_manifest.py --check    # fail if the manifest is stale
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "digiquant" / "src" / "digiquant" / "mcp_server.py"
REFUSALS = ROOT / "digiquant" / "src" / "digiquant" / "tool_refusals.py"
GLOOMBERB_ENTITLEMENTS = (
    ROOT / "digiquant" / "src" / "digiquant" / "data" / "gloomberb" / "entitlements.py"
)
LUXALGO_ENTITLEMENTS = (
    ROOT / "digiquant" / "src" / "digiquant" / "data" / "luxalgo" / "entitlements.py"
)
OUT = ROOT / "apps" / "digiquant-web" / "app" / "_mcp-tools.json"

PREFIX_FAMILIES = {
    "digifetch_": "digifetch",
    "luxalgo_": "luxalgo",
    "dashboard_": "policy",
}
KEYWORD_FAMILIES = (
    ("list_strategies", "run_", "export"),
    ("fetch_", "coinmetrics"),
    ("fit_", "build_", "generate_", "validate_"),
)
KEYWORD_FAMILY_NAMES = ("strategies", "feeds", "models")

#: Entitlements whose tools are advertised only when the deployer's own Gloomberb
#: cookie validates against api.gloom.sh. Read from ``mcp_server.py`` at run time
#: and cross-checked against this copy so a server-side change is not silently
#: ignored. This surface never carries a deployer cookie, so by default these
#: tools are not advertised. Set ``MCP_MANIFEST_ADVERTISE_GLOOMBERB_SESSION=1``
#: only for a deployment that has one and has re-audited them.
SESSION_ENTITLEMENTS_FALLBACK = frozenset({"session", "preview", "pro"})
SESSION_ENTITLEMENTS_ENV = "MCP_MANIFEST_ADVERTISE_GLOOMBERB_SESSION"

#: Tools that returned a real answer on the local stack on 2026-10-11.
#: Everything else registered is dropped; see ``AUDIT_EXCLUDED`` for the reasons
#: and the reproduction notes.
AUDITED_KEEP = frozenset(
    {            "digiquant_build_sdca_risk_index",
        "digiquant_export",
        "digiquant_fetch_bgeometrics_series",
        "digiquant_fetch_bitview_series",
        "digiquant_fetch_coinbase_ohlcv",
        "digiquant_fetch_coinmetrics_series",
        "digiquant_fit_btc_power_law",
        "digiquant_fit_sdca_weights",
        "digiquant_list_coinmetrics_catalog",
        "digiquant_run_optimize",
        "luxalgo_edge_presets",
        "luxalgo_edge_report",
        "luxalgo_edge_symbols",
        "luxalgo_library_get_concept",
        "luxalgo_library_get_indicator",
        "luxalgo_library_list_concepts",
        "luxalgo_library_list_families",
        "luxalgo_library_list_indicators",
        "luxalgo_library_list_tags",
        "luxalgo_library_search",
        "luxalgo_trackers_datasets",
        "luxalgo_trackers_latest",
        "luxalgo_trackers_ticker",
    }
)

#: Why each remaining registered tool is not advertised. Keys are tool names; the
#: value is the reason shown by ``--why``. ``digifetch_*`` is handled by
#: ``_digifetch_reason`` instead of one entry per tool.
AUDIT_EXCLUDED = {
    "digifetch_options_scenario": (
        "calls _build_gloomberb_client().options_scenario(), so it sits behind the "
        "GLOOMBERB_ENABLED kill switch. A 2026-10-11 first-pass call answered; a "
        "re-probe with the documented legs_json shape returned upstream_error, so "
        "that first-pass verdict is withdrawn."
    ),
    "digiquant_list_strategies": (
        "server defect: the tool body json.dumps()s a structure carrying Decimal "
        "default_params, so every call raises 'Object of type Decimal is not JSON "
        "serializable'. Sibling tools use model_dump_json."
    ),
    "digiquant_run_backtest": (
        "server defect: NautilusTrader writes its progress stream to stdout, the same "
        "channel as JSON-RPC, so the client gets 13032 'Failed to parse JSONRPC message "
        "from server' lines and times out. digiquant_run_optimize on the same CSV works."
    ),
    "luxalgo_library_get_family": (
        "upstream refusal: every documented family value (11 display names and the key "
        "'trend') returns a byte-identical 1131-byte 'Input validation error'."
    ),
    "digiquant_validate_slapper_vs_tradingview": (
        "needs two user-supplied CSV files; nothing on this surface holds them."
    ),
    "dashboard_get_policy_comparison": "needs a prior policy artifact id; no MCP tool seeds one.",
    "dashboard_evaluate_policy_gate": "needs a prior policy artifact id; no MCP tool seeds one.",
    "dashboard_get_policy_gate_evaluation": "needs a prior policy artifact id; no MCP tool seeds one.",
    "dashboard_get_policy_replay": "needs a prior policy artifact id; no MCP tool seeds one.",
    "dashboard_run_policy_replay": "needs a prior policy artifact id; no MCP tool seeds one.",
    "digiquant_get_macro_series": "needs SUPABASE_* configuration this surface does not carry.",
    "digiquant_query_research": "needs SUPABASE_* configuration this surface does not carry.",
    "digiquant_get_price_technicals": "needs R2 credentials this surface does not carry.",
    "digiquant_generate_slapper_tearsheet": "needs a price-history file that is not shipped with the surface.",
    "digiquant_get_trade_levels": "needs ohlc_json or a ticker; no default on this surface.",
    "digiquant_run_pipeline": "needs data_path or data_dir; no default on this surface.",
}

DIGIFETCH_REASON = (
    "the digifetch family is behind the Gloomberb kill switch: with GLOOMBERB_ENABLED "
    "unset every call returns isError=false and an upstream_error envelope saying the "
    "family is disabled. That is an environment condition, not a server defect."
)


def literal(node: ast.AST) -> Any:
    """Return the Python value of a literal-only AST node, else ``None``."""
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def string_set(node: ast.AST) -> frozenset[str]:
    """Return a frozenset from ``{...}`` or ``frozenset({...})``.

    ``frozenset({...})`` is a Call, which :func:`ast.literal_eval` refuses, so the
    wrapper is unwrapped before evaluating. Skipping that step made both gate
    branches return empty and quietly advertise every gated tool.
    """
    if isinstance(node, ast.Call) and len(node.args) == 1:
        node = node.args[0]
    value = literal(node)
    if isinstance(value, (set, frozenset, list, tuple)):
        return frozenset(str(item) for item in value)
    return frozenset()


def string_dict(node: ast.AST) -> dict[str, str]:
    """Return a dict of string keys to string values from a literal ``{...}``."""
    value = literal(node)
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items() if isinstance(v, str)}
    return {}


def find_assignment(tree: ast.AST, name: str) -> ast.AST | None:
    """Return the value node bound to ``name`` by any Assign or AnnAssign."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            if getattr(node.target, "id", None) == name and node.value is not None:
                return node.value
        elif isinstance(node, ast.Assign):
            if any(getattr(t, "id", None) == name for t in node.targets):
                return node.value
    return None


def server_facts() -> tuple[dict[str, dict[str, Any]], frozenset[str], frozenset[str]]:
    """Return (tools by name, read-scope names, session-gated entitlement names)."""
    tree = ast.parse(SERVER.read_text())
    tools: dict[str, dict[str, Any]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            fname = getattr(func, "id", None) or getattr(func, "attr", None)
            if fname != "_maybe_tool" or not dec.args:
                continue
            name = literal(dec.args[0])
            if isinstance(name, str):
                tools[name] = {
                    "name": name,
                    "summary": first_paragraph(ast.get_docstring(node) or ""),
                    "params": params(node),
                }
    read_scope = frozenset(
        literal(find_assignment(tree, "READ_SCOPE_TOOLS")) or frozenset()
    )
    session_node = find_assignment(tree, "_GLOOMBERB_SESSION_ENTITLEMENTS")
    session_entitlements = string_set(session_node) if session_node is not None else frozenset()
    return tools, read_scope, session_entitlements


def refused_names() -> frozenset[str]:
    """Return the unconditional refusal set from ``tool_refusals.py``."""
    node = find_assignment(ast.parse(REFUSALS.read_text()), "REFUSED_TOOLS")
    return string_set(node) if node is not None else frozenset()


def entitlements() -> dict[str, str]:
    """Return tool -> entitlement, Gloomberb first then LuxAlgo (as the server does)."""
    merged: dict[str, str] = {}
    for path in (GLOOMBERB_ENTITLEMENTS, LUXALGO_ENTITLEMENTS):
        node = find_assignment(ast.parse(path.read_text()), "TOOL_ENTITLEMENTS")
        if node is not None:
            merged.update(string_dict(node))
    return merged


def family(name: str) -> str:
    """Return the band a tool is grouped under on the surface."""
    for prefix, band in PREFIX_FAMILIES.items():
        if name.startswith(prefix):
            return band
    for keywords, band in zip(KEYWORD_FAMILIES, KEYWORD_FAMILY_NAMES):
        if any(keyword in name for keyword in keywords):
            return band
    return "research"


def params(node: ast.AST) -> list[dict[str, Any]]:
    """Return one ``McpParam`` per tool parameter.

    The shape is ``{name, type, required, default}`` -- the array declared by
    ``McpTool`` in ``lib/mcp-demo.ts`` and consumed by ``McpCli`` and
    ``exampleArgs``. This function used to emit a bare ``name -> type`` map, a
    shape no consumer reads; TypeScript caught it on 2026-10-12 with TS2352 when
    the manifest was regenerated. ``required`` is "has no default in the
    signature", which is what ``exampleArgs`` and the "N required" line mean.
    """
    args = getattr(node, "args")
    out: list[dict[str, Any]] = []
    positional = [*args.posonlyargs, *args.args]
    # ast.arg has no .default: positional defaults are the last len(args.defaults)
    # entries, and keyword-only defaults sit in kw_defaults (None means required).
    n_required_pos = len(positional) - len(args.defaults)
    for i, arg in enumerate(positional):
        annotation = ast.unparse(arg.annotation) if arg.annotation is not None else "str"
        required = i < n_required_pos
        out.append(
            {
                "name": arg.arg,
                "type": annotation,
                "required": required,
                "default": None if required else literal(args.defaults[i - n_required_pos]),
            }
        )
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        annotation = ast.unparse(arg.annotation) if arg.annotation is not None else "str"
        required = default is None
        out.append(
            {
                "name": arg.arg,
                "type": annotation,
                "required": required,
                "default": None if required else literal(default),
            }
        )
    for extra in (args.vararg, args.kwarg):
        if extra is not None:
            out.append({"name": extra.arg, "type": "str", "required": False, "default": None})
    return out


def first_paragraph(docstring: str) -> str:
    """Return the first paragraph of a docstring, collapsed to one line."""
    text = docstring.strip()
    if not text:
        return ""
    para = text.split("\n\n", 1)[0]
    return " ".join(para.split())


def digifetch_reason() -> str:
    return DIGIFETCH_REASON


def build() -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    """Return (kept tools, dropped name -> reason, stale audit entries)."""
    tools, read_scope, session_entitlements = server_facts()
    if session_entitlements != SESSION_ENTITLEMENTS_FALLBACK:
        print(
            f"warning: mcp_server.py gates on {sorted(session_entitlements)}, "
            f"this script knows {sorted(SESSION_ENTITLEMENTS_FALLBACK)}",
            file=sys.stderr,
        )
    refused = refused_names()
    entitlement_by_tool = entitlements()
    advertise_session = os.environ.get(SESSION_ENTITLEMENTS_ENV) == "1"

    stale = sorted(
        (AUDITED_KEEP | set(AUDIT_EXCLUDED)) - set(tools)
    )

    kept: list[dict[str, Any]] = []
    dropped: dict[str, str] = {}
    for name, tool in sorted(tools.items()):
        entitlement = entitlement_by_tool.get(name)
        if name in refused:
            dropped[name] = "refused by digiquant.tool_refusals"
            continue
        if (
            not advertise_session
            and entitlement is not None
            and entitlement in session_entitlements
        ):
            dropped[name] = (
                f"entitlement '{entitlement}' needs the deployer's Gloomberb cookie"
            )
            continue
        if name in AUDITED_KEEP:
            kept.append(
                {
                    "name": name,
                    "family": family(name),
                    "scope": "read" if name in read_scope else "full",
                    "summary": tool["summary"],
                    "params": tool["params"],
                }
            )
            continue
        if name in AUDIT_EXCLUDED:
            dropped[name] = AUDIT_EXCLUDED[name]
        elif name.startswith("digifetch_"):
            dropped[name] = digifetch_reason()
        else:
            dropped[name] = "not audited as answering on the local stack (2026-10-11)"
    kept.sort(key=lambda t: (t["family"], t["name"]))
    return kept, dropped, stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when the committed manifest differs from the generated one",
    )
    parser.add_argument("--why", action="store_true", help="print why each tool was dropped")
    args = parser.parse_args(argv)

    kept, dropped, stale = build()
    if stale:
        print(
            "error: these audit entries name a tool the server no longer defines: "
            + ", ".join(stale),
            file=sys.stderr,
        )
        return 1

    generated = json.dumps(kept, indent=2) + "\n"
    if args.why:
        for name, reason in sorted(dropped.items()):
            print(f"drop  {name}: {reason}")
    if args.check:
        current = OUT.read_text() if OUT.exists() else ""
        if current != generated:
            print(f"error: {OUT} is stale; run scripts/gen_mcp_manifest.py", file=sys.stderr)
            return 1
        print(f"ok: {OUT.name} matches the server ({len(kept)} tools)")
        return 0
    OUT.write_text(generated)
    print(f"wrote {OUT.name}: {len(kept)} tools kept, {len(dropped)} dropped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
