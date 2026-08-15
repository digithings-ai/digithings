"""Phase 1: LangGraph workflow graph tests."""

from __future__ import annotations

import logging
import sys
import types
from unittest.mock import patch

import digigraph.graph.graph as _graph_module
import pytest
from digigraph.graph import build_workflow_graph


@pytest.fixture(autouse=False)
def reset_checkpointer():
    """Reset the process-wide checkpointer singleton between tests."""
    original_instance = _graph_module._checkpointer_instance
    original_cm_holders = list(_graph_module._cm_holders)
    _graph_module._checkpointer_instance = None
    _graph_module._cm_holders = []
    yield
    _graph_module._checkpointer_instance = original_instance
    _graph_module._cm_holders = original_cm_holders


@pytest.mark.unit
def test_checkpointer_defaults_to_sqlite_when_project_active(
    tmp_path, monkeypatch, reset_checkpointer
):
    """When digiproject.yaml is present and DIGI_CHECKPOINTER is unset, resolved checkpointer is sqlite."""
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text("version: v1alpha1\nproject:\n  name: test\n")
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(cfg))
    monkeypatch.delenv("DIGI_CHECKPOINTER", raising=False)
    monkeypatch.setenv("DIGI_CHECKPOINTER_SQLITE_URI", str(tmp_path / "ckpt.sqlite"))

    ckpt = _graph_module.get_checkpointer()

    assert ckpt is not None, "Expected a checkpointer, got None"
    assert type(ckpt).__name__ == "SqliteSaver", (
        f"Expected SqliteSaver when project active, got {type(ckpt).__name__!r}"
    )


@pytest.mark.unit
def test_checkpointer_defaults_to_memory_without_project(monkeypatch, reset_checkpointer):
    """When no digiproject.yaml is present and DIGI_CHECKPOINTER is unset, resolved checkpointer is memory."""
    monkeypatch.delenv("DIGI_CHECKPOINTER", raising=False)
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)

    with patch("digigraph.project_config._resolve_config_path", return_value=None):
        ckpt = _graph_module.get_checkpointer()

    assert ckpt is not None, "Expected a checkpointer, got None"
    # LangGraph >= 1.x aliases MemorySaver -> InMemorySaver
    assert type(ckpt).__name__ in ("MemorySaver", "InMemorySaver"), (
        f"Expected memory-based checkpointer without project, got {type(ckpt).__name__!r}"
    )


@pytest.mark.unit
def test_checkpointer_env_overrides_project_default(tmp_path, monkeypatch, reset_checkpointer):
    """DIGI_CHECKPOINTER env var overrides the project-based default."""
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text("version: v1alpha1\nproject:\n  name: test\n")
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(cfg))
    monkeypatch.setenv("DIGI_CHECKPOINTER", "memory")

    ckpt = _graph_module.get_checkpointer()

    assert ckpt is not None, "Expected a checkpointer, got None"
    # LangGraph >= 1.x aliases MemorySaver -> InMemorySaver
    assert type(ckpt).__name__ in ("MemorySaver", "InMemorySaver"), (
        f"Expected memory-based checkpointer (env override), got {type(ckpt).__name__!r}"
    )


@pytest.mark.unit
def test_build_workflow_graph_compiles() -> None:
    """Graph compiles and has invoke."""
    g = build_workflow_graph()
    assert callable(g.invoke)
    graph_inner = g.get_graph()
    assert "optimize" in graph_inner.nodes


@pytest.mark.unit
def test_graph_invoke_returns_state_with_expected_keys() -> None:
    """Invoke returns state. When LLM fails, research returns error (no fallback)."""
    with patch("digigraph.graph.research.completion_text", side_effect=Exception("no-llm")):
        g = build_workflow_graph()
        out = g.invoke(
            {"prompt": "mean reversion on tech"}, config={"configurable": {"thread_id": "test"}}
        )
    assert "strategy_name" in out
    assert "symbols" in out
    assert out.get("research_note") == "error"
    assert out.get("error")
    assert "backtest_result" in out or "error" in out


@pytest.mark.unit
def test_graph_research_returns_error_when_llm_raises() -> None:
    """When LLM raises, research node returns sanitized error; no heuristic fallback."""
    with patch("digigraph.graph.research.completion_text", side_effect=Exception("unavailable")):
        g = build_workflow_graph()
        out = g.invoke({"prompt": "stat arb tech"}, config={"configurable": {"thread_id": "test"}})
    assert out.get("strategy_name") is None
    assert out.get("research_note") == "error"
    # Raw exception text is not streamed to clients (may include Compose DNS names).
    assert out.get("error") == "Research failed. Please try again shortly."
    assert "unavailable" not in str(out.get("error", ""))


@pytest.mark.unit
def test_graph_research_only_when_backtest_disabled() -> None:
    """When agents.enabled excludes backtest (e.g. Sitas), graph goes research → END."""
    mock_cfg = type("Cfg", (), {"get_enabled_agents": lambda self: ["research"]})()
    with patch("digigraph.graph.graph.DigiProjectConfig") as m:
        m.load.return_value = mock_cfg
        g = build_workflow_graph()
    with patch("digigraph.graph.research.completion_text", side_effect=Exception("no-llm")):
        out = g.invoke({"prompt": "search docs"}, config={"configurable": {"thread_id": "test"}})
    assert "backtest_result" not in out or out.get("backtest_result") is None
    assert out.get("error")


# ── Postgres checkpointer connection bounds (#1734) ──────────────────────────
#
# ``langgraph-checkpoint-postgres`` is NOT needed — the saver is faked. psycopg *is*, and it
# only arrives with the optional ``digigraph[checkpoint-postgres]`` extra, so every test that
# needs it skips rather than erroring at import time.

_BOUND_KEYS = ("connect_timeout", "keepalives", "keepalives_idle", "keepalives_interval")


def _conninfo_params(conn_string: str) -> dict[str, str]:
    from psycopg.conninfo import conninfo_to_dict

    return {k: str(v) for k, v in conninfo_to_dict(conn_string).items()}


@pytest.fixture
def fake_postgres_saver(monkeypatch):
    """Install a fake ``langgraph.checkpoint.postgres`` and record the conninfo it gets."""
    received: list[str] = []

    class _FakeSaver:
        def setup(self) -> None:
            """No-op: the real ``setup()`` issues DDL over a live connection."""

    class _FakeCm:
        def __enter__(self):
            return _FakeSaver()

        def __exit__(self, *_exc) -> bool:
            return False

    class _FakePostgresSaver:
        @staticmethod
        def from_conn_string(conn_string: str) -> _FakeCm:
            received.append(conn_string)
            return _FakeCm()

    module = types.ModuleType("langgraph.checkpoint.postgres")
    module.PostgresSaver = _FakePostgresSaver  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.postgres", module)
    return received


@pytest.mark.unit
def test_postgres_checkpointer_conninfo_carries_connection_bounds(
    monkeypatch, reset_checkpointer, fake_postgres_saver
):
    """The conninfo handed to ``PostgresSaver.from_conn_string`` must carry a connect
    timeout and TCP keepalives. Without them a peer that vanishes without an RST leaves
    the socket ESTABLISHED forever — the 2026-07-30 shape, 210 min of silence inside a
    240-min job (#1734). psycopg exposes no kwarg for these, so the conninfo is the seam.
    """
    pytest.importorskip("psycopg")
    monkeypatch.setenv("DIGI_CHECKPOINTER", "postgres")
    monkeypatch.setenv(
        "DIGI_CHECKPOINTER_POSTGRES_URI", "postgresql://u:p@db.example.test:5432/postgres"
    )

    ckpt = _graph_module.get_checkpointer()

    assert ckpt is not None, "Expected the faked PostgresSaver, got None"
    assert len(fake_postgres_saver) == 1
    params = _conninfo_params(fake_postgres_saver[0])
    assert params["host"] == "db.example.test", "credentials/host must survive the rewrite"
    assert params["password"] == "p"
    for key in _BOUND_KEYS:
        assert key in params, f"{key} missing from the checkpointer conninfo"
    assert params["connect_timeout"] == "10"
    assert params["keepalives"] == "1"


@pytest.mark.unit
def test_bounded_conn_string_accepts_keyword_value_form():
    """libpq allows ``host=... dbname=...`` as well as a URI; both must be bounded."""
    pytest.importorskip("psycopg")
    out = _graph_module._bounded_conn_string("host=db.example.test dbname=postgres user=u")
    params = _conninfo_params(out)
    assert params["dbname"] == "postgres"
    for key in _BOUND_KEYS:
        assert key in params


@pytest.mark.unit
def test_bounded_conn_string_preserves_operator_overrides():
    """A value already in DIGI_CHECKPOINTER_POSTGRES_URI wins — that env var is the
    documented escape hatch, so the defaults must never overwrite it."""
    pytest.importorskip("psycopg")
    out = _graph_module._bounded_conn_string(
        "postgresql://db.example.test/postgres?connect_timeout=45&keepalives_idle=600"
    )
    params = _conninfo_params(out)
    assert params["connect_timeout"] == "45"
    assert params["keepalives_idle"] == "600"
    assert params["keepalives"] == "1"  # still filled in


@pytest.mark.unit
def test_bounded_conn_string_returns_unparseable_input_unchanged(caplog):
    """Bounding is best-effort: a malformed conninfo must warn and pass through, never
    raise. Whatever error the operator has is theirs to see from psycopg, not from us."""
    pytest.importorskip("psycopg")
    raw = "this is not a conninfo"
    with caplog.at_level(logging.WARNING):
        assert _graph_module._bounded_conn_string(raw) == raw
    assert "not parseable" in caplog.text
    assert raw not in caplog.text, "a conninfo can contain the DB password; never log it"


@pytest.mark.unit
def test_bounded_conn_string_returns_input_unchanged_without_psycopg(monkeypatch):
    """Deployments without the ``checkpoint-postgres`` extra have no psycopg. Missing the
    bounds is the status quo; an ImportError at graph-build time would be a regression."""
    monkeypatch.setitem(sys.modules, "psycopg.conninfo", None)
    raw = "postgresql://db.example.test/postgres"
    assert _graph_module._bounded_conn_string(raw) == raw


@pytest.mark.unit
def test_static_interrupt_after_pauses_but_resume_value_is_silently_dropped() -> None:
    """Regression test for the digigraph HITL gap: server.py's /threads/{id}/resume
    endpoint calls graph.invoke(Command(resume=resume_value), config=config)
    (server.py:457-480), but digigraph wires ONLY a static, compile-time
    interrupt_after=["research"] breakpoint (graph.py:277-285) -- no node calls
    interrupt(). This proves BOTH halves of that gap on a graph built exactly the way
    digigraph builds one (same compile(checkpointer=..., interrupt_after=[...]) shape):

    1. interrupt_after really does pause execution (get_state().next shows the pending
       node -- empirically confirmed this is NOT a no-op).
    2. Command(resume=...)'s value is silently dropped: a node downstream of the pause
       has no way to see it, because nothing is waiting on an interrupt() call to
       receive it.

    If a future fix replaces the static breakpoint with a real interrupt() call, THIS
    test must start asserting the resume value DOES arrive -- if it is still green
    after that change, the fix did not work.
    """
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command
    from typing_extensions import TypedDict

    class _State(TypedDict, total=False):
        step: str
        approved: bool

    def research(state: _State) -> dict:
        return {"step": "researched"}

    def validate(state: _State) -> dict:
        # A real interrupt()-based node would read the resume value here via
        # interrupt(...)'s return value. This node has no such call -- exactly
        # digigraph's strategy_validator_node today -- so it can only ever see
        # whatever was already in state, never what Command(resume=...) carried.
        return {"step": "validated", "approved": state.get("approved", False)}

    g: StateGraph[_State] = StateGraph(_State)
    g.add_node("research", research)
    g.add_node("validate", validate)
    g.add_edge(START, "research")
    g.add_edge("research", "validate")
    g.add_edge("validate", END)
    compiled = g.compile(checkpointer=InMemorySaver(), interrupt_after=["research"])

    config = {"configurable": {"thread_id": "hitl-regression-1"}}
    first = compiled.invoke({"step": "start"}, config=config)
    assert first == {"step": "researched"}, "must pause before validate runs"

    paused = compiled.get_state(config)
    assert paused.next == ("validate",), (
        f"expected the graph paused with 'validate' pending, got next={paused.next!r}"
    )

    resumed = compiled.invoke(Command(resume="approved-by-human"), config=config)
    assert resumed == {"step": "validated", "approved": False}, (
        "the resume value was silently dropped, exactly as digigraph's current wiring "
        "does today -- if this assertion fails, someone added a real interrupt() call "
        "and this test must be updated to assert the NEW, fixed behavior instead"
    )
