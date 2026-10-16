"""Dummy-plugin conformance test for the digiquant plugin surface (DIG-3691).

R0 CI proves the ``digiquant.plugin`` contract with a synthetic plugin rather
than the real private distribution: a fake ``digiquant.strategies`` entry
point must reach the strategy registry, a fake ``digiquant.mcp_tools`` entry
point must observe ``(mcp, maybe_tool)``, a fake ``digiquant.cli`` entry
point must observe ``main``, the SDCA hooks must resolve through the plugin
first, and a broken entry point must warn-and-skip instead of raising.
"""

from __future__ import annotations

import warnings

import pytest

pytestmark = pytest.mark.unit


class _FakeEntryPoint:
    def __init__(self, name, loaded=None, fail=False):
        self.name = name
        self._loaded = loaded
        self._fail = fail

    def load(self):
        if self._fail:
            raise RuntimeError("broken dummy entry point")
        return self._loaded


def _patch_discover(monkeypatch, mapping):
    from digiquant import plugin as plugin

    def _fake(group):
        return list(mapping.get(group, []))

    monkeypatch.setattr(plugin, "discover", _fake)


def test_strategy_plugin_registers_through_entry_point(monkeypatch):
    from digiquant import plugin as plugin

    seen = []

    def _dummy_register(register_fn):
        register_fn(
            "dummy_plugin_strategy",
            object,
            object,
            {"p": 1},
            description="dummy",
        )
        seen.append("dummy_plugin_strategy")

    _patch_discover(
        monkeypatch,
        {plugin.STRATEGIES_GROUP: [_FakeEntryPoint("dummy", loaded=_dummy_register)]},
    )
    calls = []
    count = plugin.register_plugin_strategies(lambda *a, **k: calls.append((a, k)))
    assert count == 1
    assert len(calls) == 1
    assert seen == ["dummy_plugin_strategy"]


def test_mcp_and_cli_plugins_observe_expected_args(monkeypatch):
    from digiquant import plugin as plugin

    mcp_seen = []
    cli_seen = []

    def _dummy_mcp(mcp, maybe_tool):
        mcp_seen.append((mcp, maybe_tool))

    def _dummy_cli(main):
        cli_seen.append(main)

    _patch_discover(
        monkeypatch,
        {
            plugin.MCP_TOOLS_GROUP: [_FakeEntryPoint("dummy-mcp", loaded=_dummy_mcp)],
            plugin.CLI_GROUP: [_FakeEntryPoint("dummy-cli", loaded=_dummy_cli)],
        },
    )
    assert plugin.register_plugin_mcp_tools("MCP", "MAYBE_TOOL") == 1
    assert mcp_seen == [("MCP", "MAYBE_TOOL")]
    assert plugin.register_plugin_cli("MAIN") == 1
    assert cli_seen == ["MAIN"]


def test_object_protocol_and_broken_entry_point_warns_not_raises(monkeypatch):
    from digiquant import plugin as plugin

    class _Obj:
        def __init__(self):
            self.calls = []

        def register_cli(self, main):
            self.calls.append(main)

    obj = _Obj()
    _patch_discover(
        monkeypatch,
        {
            plugin.CLI_GROUP: [
                _FakeEntryPoint("good", loaded=obj),
                _FakeEntryPoint("broken", fail=True),
            ],
        },
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert plugin.register_plugin_cli("MAIN") == 1
    assert obj.calls == ["MAIN"]
    assert any("broken" in str(w.message) for w in caught)


def test_sdca_hooks_resolve_plugin_first(monkeypatch):
    from digiquant import plugin as plugin

    sentinel_opt = object()
    sentinel_risk = object()

    class _Plugin:
        def run_sdca_optimize(self, **kwargs):
            return sentinel_opt

        def materialize_sdca_risk_index(self, *args, **kwargs):
            return sentinel_risk

        @staticmethod
        def power_law_fns():
            return ("fit", "save")

    _patch_discover(
        monkeypatch,
        {plugin.STRATEGIES_GROUP: [_FakeEntryPoint("dummy", loaded=_Plugin())]},
    )
    # Hooks resolve through the plugin; note _Plugin() is an object, not a
    # register-callable, so register_plugin_strategies skips it (warns) — the
    # attrs are still discoverable for hooks.
    assert plugin.get_sdca_optimize_hook() is not None
    assert plugin.get_risk_index_hook() is not None
    assert plugin.get_power_law_hook() == ("fit", "save")


def test_no_plugin_means_no_hook(monkeypatch):
    from digiquant import plugin as plugin

    _patch_discover(monkeypatch, {})
    assert plugin.get_sdca_optimize_hook() is None
    assert plugin.get_risk_index_hook() is None
    assert plugin.get_power_law_hook() is None
    assert plugin.register_plugin_strategies(lambda *a, **k: None) == 0
    assert plugin.register_plugin_mcp_tools(None, None) == 0
    assert plugin.register_plugin_cli(None) == 0


def test_charts_registry_roundtrip():
    from digiquant import plugin as plugin

    marker = object()
    plugin.register_chart("dummy.test_chart", marker)
    assert "dummy.test_chart" in plugin.list_charts()
    assert plugin.get_chart("dummy.test_chart") is marker


def test_strategies_init_discovers_plugins(monkeypatch):
    """strategies/__init__ must consult the plugin (entry-point discovery)."""
    import sys

    from digiquant import plugin as plugin

    calls = []
    monkeypatch.setattr(plugin, "register_plugin_strategies", lambda r: calls.append(r) or 0)
    for name in list(sys.modules):
        if name == "digiquant.strategies" or name.startswith("digiquant.strategies."):
            del sys.modules[name]
    import digiquant.strategies as strategies

    assert len(calls) == 1
    assert calls[0] is strategies.register
