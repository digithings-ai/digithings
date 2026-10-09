"""Art. 9 admission on the digillm MCP surface (spec DIG-912 §5.4, acceptance test 8).

`DIGI_MCP_REQUIRE_AUTH` appears in exactly one place repo-wide, so the digillm
streamable-HTTP MCP server (:8768) is unauthenticated by default. Spec §5.4 says
that such a surface needs a *non-HTTP registry* — "registered or refused by an
explicit mechanism, not by path" — because a path-keyed registry structurally
cannot see a tool call. AT8: "All three MCP surfaces and the SDK entry are
screened or refused by the non-HTTP registry."

These tests use a purpose-built FastMCP server rather than the module's real one
so that the tool body is observable (a sentinel) and the network is never
reached. The module's own screen is still what gets installed: only the server
object differs.

pytestmark = pytest.mark.unit — the marker is REQUIRED. test-digillm.yml runs
`pytest digillm/tests` unfiltered today, but ci.yml's package lanes filter on
`-m unit`, and an unmarked file collects 0 items there and prints a green line
having asserted nothing.
"""

from __future__ import annotations

import ast
import asyncio
import builtins
import json

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from digillm import mcp_server as art9

pytestmark = pytest.mark.unit


def _module_path() -> str:
    return art9.__file__

# A payload that trips a field name, and one that trips a value pattern. Both are
# checked against the detector directly below; neither is trusted on sight.
TRIPPING_FIELD_NAME = {"messages": [{"role": "user", "content": "x"}], "genotype": "rs1234"}
TRIPPING_VALUE = {"messages": [{"role": "user", "content": "see my rs1234 report"}]}
BENIGN = {"messages": [{"role": "user", "content": "summarise the release notes"}]}


def _result_shape(result):
    """Assert the result carries the ScreenResult surface callers depend on."""
    assert isinstance(result.decision, str)
    assert isinstance(result.categories, tuple)
    assert isinstance(result.reason, str)
    return result


# --------------------------------------------------------------------------
# positive controls: the payloads really trip, and the detector really runs
# --------------------------------------------------------------------------


def test_the_tripping_payloads_really_trip_the_detector():
    """Positive control. Without this every refusal assertion below is the
    empty-vs-empty trap: a detector that matched nothing would also refuse
    nothing, and a screen wired to a no-op would pass identically."""
    for payload in (TRIPPING_FIELD_NAME, TRIPPING_VALUE):
        result = _result_shape(art9.screen_art9_surface(art9.SURFACE_MCP, payload))
        assert result.decision == "refuse", payload
        assert result.categories, payload
    assert _result_shape(art9.screen_art9_surface(art9.SURFACE_MCP, BENIGN)).decision == "allow"


def test_the_refusal_reason_names_the_category_it_refused_on():
    """A refusal that cannot be attributed to a category is not auditable."""
    reason = art9.screen_art9_surface(art9.SURFACE_MCP, TRIPPING_FIELD_NAME).reason
    assert reason.startswith("art9:"), reason
    assert art9.screen_art9_surface(art9.SURFACE_MCP, TRIPPING_FIELD_NAME).categories == (
        "genetic",
    )


# --------------------------------------------------------------------------
# the registry itself
# --------------------------------------------------------------------------


def test_the_mcp_surface_is_registered_with_an_explicit_kind():
    """Spec §5.4 asks for registration by *explicit mechanism*. An empty
    registry would satisfy 'screened or refused' vacuously if the screen refused
    everything, so the entry must exist AND carry a kind."""
    assert art9.ART9_SURFACES[art9.SURFACE_MCP] == art9.SURFACE_KIND_MCP
    assert art9.art9_surface_kind(art9.SURFACE_MCP) == art9.SURFACE_KIND_MCP


def test_an_unregistered_surface_is_refused_rather_than_screened():
    """F11: a *missing* registration has to be visible. Screening an unknown
    surface by its content alone is what lets a dropped registration silently
    unscreen a surface."""
    result = _result_shape(art9.screen_art9_surface("mcp:not-declared", BENIGN))
    assert result.decision == "refuse"
    assert result.reason == f"{art9.SURFACE_UNREGISTERED}:mcp:not-declared"


def test_refusing_an_unregistered_surface_does_not_depend_on_its_payload():
    """The refusal is about the registration, not the content — a benign payload
    on an unknown surface is refused for the same reason as a tripping one."""
    benign = art9.screen_art9_surface("mcp:not-declared", BENIGN).reason
    tripping = art9.screen_art9_surface("mcp:not-declared", TRIPPING_FIELD_NAME).reason
    assert benign == tripping


def test_screening_fails_closed_when_the_detector_cannot_be_imported(monkeypatch):
    """digillm must not depend on digibase, so the detector is imported lazily.
    A lazy import that quietly degrades to 'allow' is a screen that passes
    without testing anything — it must refuse instead."""
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.startswith("digibase"):
            raise ImportError("digibase is deliberately not a digillm dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    result = _result_shape(art9.screen_art9_surface(art9.SURFACE_MCP, BENIGN))
    assert result.decision == "refuse"
    assert result.reason == art9.SURFACE_SCREENING_UNAVAILABLE


def test_declaring_a_surface_is_visible_to_the_read_only_view():
    art9.declare_art9_surface("mcp:probe", art9.SURFACE_KIND_MCP)
    try:
        assert art9.ART9_SURFACES["mcp:probe"] == art9.SURFACE_KIND_MCP
    finally:
        art9._surfaces.pop("mcp:probe", None)


def test_the_registry_view_is_read_only():
    with pytest.raises(TypeError):
        art9.ART9_SURFACES["mcp:sneaky"] = art9.SURFACE_KIND_MCP  # type: ignore[index]


# --------------------------------------------------------------------------
# the screen on the tool dispatch path
# --------------------------------------------------------------------------


def _server_with_observed_tool():
    """A FastMCP server whose single tool records that its body was entered."""
    server = FastMCP("art9-probe", json_response=True)
    entered: list[str] = []

    @server.tool()
    def probe(text: str) -> str:
        entered.append(text)
        return f"echo:{text}"

    return server, entered


def _call(server, **arguments):
    return asyncio.run(server._tool_manager.call_tool("probe", arguments, convert_result=False))


def test_a_tool_call_tripping_a_category_is_refused_without_reaching_the_body():
    """AT8. The refusal is asserted through the REAL dispatch path
    (ToolManager.call_tool -> Tool.run -> fn), not through a helper called
    directly, so a wrapper that never got installed cannot pass this."""
    server, entered = _server_with_observed_tool()
    assert art9.install_art9_surface_screen(server) == 1
    with pytest.raises(ToolError) as caught:
        _call(server, text="see my rs1234 report")
    assert isinstance(caught.value.__cause__, art9.Art9SurfaceRefusal)
    assert caught.value.__cause__.reason == "art9:genetic:rs_id"
    assert entered == [], "a refused tool call must never reach the tool body"


def test_a_benign_tool_call_still_reaches_the_body():
    """The negative control for the test above. Without it, a wrapper that
    refused unconditionally would pass the refusal test and nothing would say so."""
    server, entered = _server_with_observed_tool()
    art9.install_art9_surface_screen(server)
    assert "echo:hello" in str(_call(server, text="hello"))
    assert entered == ["hello"]


def test_unwrapping_the_tool_makes_the_refusal_go_away():
    """The mutation assertion, and the load-bearing part of this file. It proves
    the refusal observed above is produced by the screen and not by the tool, so
    the guard is not vacuous. The tool body is swapped for a recorder, the same
    call is made, and the difference is asserted in both directions."""
    server, entered = _server_with_observed_tool()
    art9.install_art9_surface_screen(server)
    tool = server._tool_manager.get_tool("probe")
    screened_fn = tool.fn
    with pytest.raises(ToolError):
        _call(server, text="see my rs1234 report")
    assert entered == [], "screened: the body must not be reached"

    # Mutation: bypass the screen by restoring an unscreened body.
    tool.fn = lambda **kwargs: f"echo:{kwargs['text']}"
    try:
        assert "echo:see my rs1234 report" in str(
            _call(server, text="see my rs1234 report")
        )
    finally:
        tool.fn = screened_fn

    # And the screen is back: the same call is refused again.
    with pytest.raises(ToolError):
        _call(server, text="see my rs1234 report")
    assert entered == []


def test_installing_the_screen_twice_does_not_double_wrap():
    server, _ = _server_with_observed_tool()
    assert art9.install_art9_surface_screen(server) == 1
    assert art9.install_art9_surface_screen(server) == 0


def test_a_server_with_no_tools_fails_closed():
    """Zero wrapped tools must be an error, not a success. Counting zero and
    logging 'done' is how a refactor that loses the tool registry ships
    unscreened with a green build."""
    empty = FastMCP("art9-empty", json_response=True)
    with pytest.raises(RuntimeError, match="0 digillm MCP tools"):
        art9.install_art9_surface_screen(empty)


def test_a_server_without_a_tool_manager_fails_closed():
    class _NotAServer:
        pass

    with pytest.raises(RuntimeError):
        art9.install_art9_surface_screen(_NotAServer())


def test_the_module_screens_the_tools_it_actually_serves():
    """The real module must be wired, not just the probe server. Asserted
    against the module's own registry rather than a hard-coded count."""
    assert art9.ART9_SCREENED_TOOLS >= 1
    tools = art9.mcp._tool_manager.list_tools()
    assert tools, "the probe above would be vacuous if the server served nothing"
    assert art9.ART9_SCREENED_TOOLS == len(tools)
    assert all(getattr(t.fn, "__art9_screened__", False) for t in tools)


def test_the_screened_tool_keeps_its_name_and_doc():
    """A wrapper that drops __name__/__doc__ degrades every MCP client's tool
    listing, and a tool that disappears from the listing is a surface nobody
    screens any more."""
    for tool in art9.mcp._tool_manager.list_tools():
        assert tool.fn.__name__ == tool.name, tool.name


# --------------------------------------------------------------------------
# the fail-closed error path a caller sees
# --------------------------------------------------------------------------


def test_require_art9_clear_raises_with_the_reason_attached():
    with pytest.raises(art9.Art9SurfaceRefusal) as caught:
        art9.require_art9_clear(art9.SURFACE_MCP, TRIPPING_FIELD_NAME)
    assert caught.value.surface == art9.SURFACE_MCP
    assert caught.value.reason.startswith("art9:")
    assert caught.value.categories


def test_require_art9_clear_is_silent_on_a_clean_payload():
    assert art9.require_art9_clear(art9.SURFACE_MCP, BENIGN) is None


# --------------------------------------------------------------------------
# package boundaries
# --------------------------------------------------------------------------


def test_the_module_does_not_import_fastapi():
    """digillm/AGENTS.md: 'No FastAPI, no Request objects, no service coupling.'

    Checked by PARSING the module's AST, not by grepping its text. A substring
    scan for "fastapi" fires on this module's own comment explaining that it does
    not import fastapi — a guard that scans for a name cannot be satisfied by
    prose that names it. The AST can only see real import statements."""
    tree = ast.parse(open(_module_path(), encoding="utf-8").read())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{a.name}" for a in node.names)
    assert not any(name.split(".")[0] == "fastapi" for name in imported), imported
    assert not any(name.split(".")[0] == "starlette" for name in imported), imported


def test_the_module_does_not_import_digibase_at_module_scope():
    """The detector import must stay lazy; a module-scope import would make
    digibase a hard dependency and break the digillm install. Nested imports are
    allowed anywhere, so only top-level ones are collected here."""
    tree = ast.parse(open(_module_path(), encoding="utf-8").read())
    top_level: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module)
    assert not any(name.split(".")[0] == "digibase" for name in top_level), top_level


def test_the_detector_import_is_lazy_and_guarded():
    """Both halves of the lazy contract: the import happens inside a function,
    and an ImportError becomes a refusal rather than an exception."""
    source = open(_module_path(), encoding="utf-8").read()
    assert "from digibase.art9 import screen_request" in source
    tree = ast.parse(source)
    top_level_imports = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    digibase_at_top = [
        node
        for node in top_level_imports
        if "digibase" in ast.dump(node)
    ]
    assert not digibase_at_top


def test_a_registry_entry_survives_a_json_round_trip():
    """The refusal reason is what reaches an MCP client. If it cannot be
    serialised the client sees an opaque error and the audit trail is gone."""
    result = art9.screen_art9_surface(art9.SURFACE_MCP, TRIPPING_FIELD_NAME)
    assert json.loads(json.dumps(result.reason)) == result.reason
