"""Build workflow graph: optional supervisor → research subgraph → validate → backtest (profile-driven)."""

from __future__ import annotations

import os
import threading

from langgraph.graph import END, START, StateGraph

from digigraph.graph.nodes import (
    backtest_node,
    optimize_node,
    strategy_validator_node,
    supervisor_node,
)
from digigraph.graph.research_subgraph import build_research_subgraph
from digigraph.graph.state import WorkflowState
from digigraph.project_config import DigiProjectConfig

# Shared checkpointer so thread_id persists across HTTP requests (see LANGGRAPH_REVIEW.md).
_checkpointer_lock = threading.Lock()
_checkpointer_instance: object | None = None
_workflow_graph_lock = threading.Lock()
_workflow_graph_cache: object | None = None
# Hold context managers so they are not garbage-collected (sqlite/postgres).
_cm_holders: list[object] = []
_store_lock = threading.Lock()
_store_instance: object | None = None

WORKFLOW_PROFILES = frozenset({"full_stack", "research_rag", "quant_backtest", "plan_execute"})

# libpq connection bounds for the Postgres checkpointer (#1734).
#
# ``PostgresSaver.from_conn_string`` forwards the string straight to
# ``psycopg.Connection.connect``, which applies no timeout and no TCP keepalives of its
# own, and exposes no kwarg for either. A peer that disappears mid-session without sending
# an RST therefore leaves the socket in ESTABLISHED indefinitely and the only bound left is
# the 240-minute CI job timeout — the shape of the 2026-07-30 dashboard stall, where a
# checkpoint-write boundary was followed by 210 minutes of total silence. libpq accepts all
# of these as ordinary connection parameters, so they can be merged into the conninfo
# without a kwarg ``from_conn_string`` does not have.
#
# ``connect_timeout`` bounds *establishing* a connection; the keepalive trio bounds an
# *established but dead* one (30s idle + 5 probes x 10s ~= 80s to detect). The keepalives
# are the load-bearing half — the observed stall began after connection setup.
#
# Deliberately absent: ``statement_timeout``. It is enforced server-side, so it cannot help
# when the network path is gone (the client never hears the cancellation either), and it
# risks aborting a legitimately slow write against a checkpoint table that is already
# ~950 MB in production (#1758).
_CHECKPOINTER_CONN_BOUNDS: dict[str, int] = {
    "connect_timeout": 10,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5,
}

# No node-level RetryPolicy on backtest/optimize (deliberate, not an oversight): both
# nodes already catch httpx.RequestError (among other transient errors) INSIDE their own
# function body via _DIGIQUANT_CLIENT_ERRORS (nodes.py) and return a normal error-state
# dict rather than letting the exception propagate. LangGraph's node-level retry only
# fires on an exception escaping the node function -- which never happens here, so a
# RetryPolicy on these nodes would be pure dead code (it could never actually trigger).
#
# Letting httpx.RequestError propagate instead, so a real RetryPolicy *could* fire,
# would introduce a duplicate-request risk: these are POST calls to digiquant with no
# idempotency-key protection (only a correlation X-Request-ID), so a network-blip retry
# could kick off two backtest/optimize runs. Adding real idempotency support to
# digiquant is out of scope here -- a separate service, a separate body of work. See
# tests/dg/test_graph_profiles.py::test_backtest_and_optimize_nodes_have_no_retry_policy.


def _bounded_conn_string(conn_string: str) -> str:
    """Return ``conn_string`` with connect-timeout and TCP-keepalive params filled in.

    Accepts either libpq spelling — a ``postgresql://`` URI or ``host=... dbname=...``
    keyword/value — because ``psycopg.conninfo.make_conninfo`` normalizes both and
    round-trips percent-escaped credentials that manual URL surgery mangles. Any parameter
    the operator already set in ``DIGI_CHECKPOINTER_POSTGRES_URI`` wins, so the env var
    remains the override path.

    Best-effort by design: if psycopg is absent or the string does not parse, it is
    returned unchanged. Bounding a connection must never itself be why a run fails to
    start. Never log the conninfo — it carries the database password.
    """
    try:
        from psycopg import ProgrammingError
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
    except ImportError:  # psycopg arrives with digigraph[checkpoint-postgres]
        return conn_string
    try:
        preset = conninfo_to_dict(conn_string)
        missing = {k: v for k, v in _CHECKPOINTER_CONN_BOUNDS.items() if k not in preset}
        if not missing:
            return conn_string
        return make_conninfo(conn_string, **missing)
    except ProgrammingError as exc:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "DIGI_CHECKPOINTER_POSTGRES_URI is not parseable (%s); connecting without "
            "explicit connect-timeout/keepalive bounds",
            exc,
        )
        return conn_string


# Sync checkpointers (SqliteSaver/PostgresSaver, not the Async* variants) are correct
# here because every call site in workflow.py is a plain `def` (FastAPI runs these off
# the event loop in its own threadpool already). If any route here ever becomes
# `async def`, the checkpointer selection below must move to AsyncSqliteSaver /
# AsyncPostgresSaver in lockstep, or graph.compile(checkpointer=...) raises at runtime.
def get_checkpointer():
    """
    Return a process-wide checkpointer for the current DIGI_CHECKPOINTER setting.
    The same instance is reused so thread state persists across requests.

    Env: DIGI_CHECKPOINTER=memory|sqlite|postgres. Unset defaults to **sqlite**
    when a digiproject.yaml is active (project multi-turn mode) so conversation state
    survives across requests. Falls back to **memory** when no project config is present.
    Use ``none`` to compile without one (not recommended; breaks multi-turn / thread APIs).

    For sqlite: DIGI_CHECKPOINTER_SQLITE_URI (default ~/.digigraph/checkpoints.sqlite).
    For postgres: DIGI_CHECKPOINTER_POSTGRES_URI (required for HA / multi-replica; see
    digigraph/ARCHITECTURE.md §5.5.1 — REM-099). Its conninfo is passed through
    :func:`_bounded_conn_string`, which fills in connect-timeout and TCP-keepalive
    parameters so a vanished peer cannot stall the process indefinitely (#1734).
    """
    global _checkpointer_instance, _cm_holders
    raw = (os.environ.get("DIGI_CHECKPOINTER") or "").strip().lower()
    if raw in ("none", "off", "0", "false", "disabled"):
        return None
    if raw:
        kind = raw
    else:
        from digigraph.project_config import _resolve_config_path

        kind = "sqlite" if _resolve_config_path() is not None else "memory"
    with _checkpointer_lock:
        if _checkpointer_instance is not None:
            return _checkpointer_instance
        if kind == "memory":
            try:
                from langgraph.checkpoint.memory import MemorySaver

                _checkpointer_instance = MemorySaver()
            except ImportError:
                pass
        elif kind == "sqlite":
            try:
                from langgraph.checkpoint.sqlite import SqliteSaver

                uri = os.environ.get("DIGI_CHECKPOINTER_SQLITE_URI", "").strip()
                if not uri:
                    uri = os.path.join(os.path.expanduser("~"), ".digigraph", "checkpoints.sqlite")
                    os.makedirs(os.path.dirname(uri), exist_ok=True)
                cm = SqliteSaver.from_conn_string(uri)
                _cm_holders.append(cm)
                _checkpointer_instance = cm.__enter__()
            except ImportError:
                import logging as _logging

                _logging.getLogger(__name__).warning(
                    "langgraph-checkpoint-sqlite not installed; falling back to MemorySaver. "
                    "Install with: pip install 'digigraph[checkpoint-sqlite]'"
                )
                try:
                    from langgraph.checkpoint.memory import MemorySaver

                    _checkpointer_instance = MemorySaver()
                except ImportError:
                    pass
        elif kind == "postgres":
            try:
                from langgraph.checkpoint.postgres import PostgresSaver

                conn_string = os.environ.get("DIGI_CHECKPOINTER_POSTGRES_URI", "").strip()
                if conn_string:
                    cm = PostgresSaver.from_conn_string(_bounded_conn_string(conn_string))
                    _cm_holders.append(cm)
                    _checkpointer_instance = cm.__enter__()
                    _checkpointer_instance.setup()
            except ImportError:
                pass
        return _checkpointer_instance


def get_store():
    """Return a process-wide Store for cross-thread, per-subject memory.

    Distinct from the checkpointer above, which is scoped to a single thread_id: this is
    for values that should survive a user opening a brand-new thread (e.g. a response-
    language preference). Mirrors DIGI_CHECKPOINTER's kind selection where it makes
    sense: DIGI_CHECKPOINTER=postgres gets a real PostgresStore (same conn string,
    reusing _bounded_conn_string's connect-timeout/keepalive bounds); every other kind
    (memory/sqlite/unset) gets an InMemoryStore. LangGraph ships no first-class Store
    equivalent of SqliteSaver, so mapping "sqlite" to InMemoryStore here is a documented,
    same-process choice -- not a silent degradation the way an unreachable postgres
    connection is for get_checkpointer() (that one is deliberately loud; see the
    ImportError/missing-URI branch below, which matches that same discipline).
    """
    global _store_instance
    raw = (os.environ.get("DIGI_CHECKPOINTER") or "").strip().lower()
    with _store_lock:
        if _store_instance is not None:
            return _store_instance
        if raw == "postgres":
            conn_string = os.environ.get("DIGI_CHECKPOINTER_POSTGRES_URI", "").strip()
            if conn_string:
                try:
                    from langgraph.store.postgres import PostgresStore

                    cm = PostgresStore.from_conn_string(_bounded_conn_string(conn_string))
                    _cm_holders.append(cm)
                    _store_instance = cm.__enter__()
                    _store_instance.setup()
                except ImportError:
                    import logging as _logging

                    _logging.getLogger(__name__).warning(
                        "langgraph-checkpoint-postgres not installed; falling back to "
                        "InMemoryStore for cross-thread memory. Install with: "
                        "pip install 'digigraph[checkpoint-postgres]'"
                    )
            else:
                import logging as _logging

                _logging.getLogger(__name__).warning(
                    "DIGI_CHECKPOINTER=postgres but DIGI_CHECKPOINTER_POSTGRES_URI is "
                    "unset; falling back to InMemoryStore for cross-thread memory (not "
                    "persistent, not shared across replicas)."
                )
        if _store_instance is None:
            from langgraph.store.memory import InMemoryStore

            _store_instance = InMemoryStore()
        return _store_instance


def resolve_workflow_profile() -> str:
    try:
        p = DigiProjectConfig.load().get_workflow_profile()
    except Exception:
        return "full_stack"
    return p if p in WORKFLOW_PROFILES else "full_stack"


def _route_after_supervisor(state: WorkflowState):
    if state.get("error"):
        return END
    return "research"


def _digiquant_configured() -> bool:
    """True when digiquant HTTP may run.

    Explicit empty ``DIGIQUANT_URL=`` (Profile A / chat-only) disables backtest.
    Unset env keeps the historical default URL in ``backtest_node``.
    """
    if "DIGIQUANT_URL" not in os.environ:
        return True
    return bool(os.environ.get("DIGIQUANT_URL", "").strip())


def _route_after_research(state: WorkflowState):
    if state.get("error"):
        return END
    profile = (state.get("workflow_profile") or resolve_workflow_profile()).lower()
    if profile == "research_rag":
        return END
    # Chat-only / Profile A: digiquant not deployed — never enter backtest_node.
    if not _digiquant_configured():
        return END
    # Document / RAG assistant mode: no strategy extraction → skip quant path.
    if state.get("research_response") and not state.get("strategy_name"):
        return END
    try:
        if "backtest" not in DigiProjectConfig.load().get_enabled_agents():
            return END
    except Exception:
        return END
    return "validate_strategy"


def _route_after_validate(state: WorkflowState):
    if state.get("error"):
        return END
    return "backtest"


def _optimize_after_backtest_enabled() -> bool:
    if os.environ.get("DIGI_GRAPH_OPTIMIZE_AFTER_BACKTEST", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return True
    try:
        return "optimize" in DigiProjectConfig.load().get_enabled_agents()
    except Exception:
        return False


def _route_after_backtest(state: WorkflowState):
    if state.get("error"):
        return END
    if not state.get("backtest_result"):
        return END
    if _optimize_after_backtest_enabled():
        return "optimize"
    return END


def build_workflow_graph():
    """
    Compile the workflow graph.

    - research step uses a **compiled subgraph** (same state schema).
    - Profiles (``graph.workflow_profile`` or ``DIGI_WORKFLOW_PROFILE``): full_stack,
      research_rag, quant_backtest, plan_execute (plan_execute topology = full_stack;
      use ``agents.planning_mode`` for planner behavior).
    - Optional supervisor when ``DIGI_SUPERVISOR=1``.
    """
    global _workflow_graph_cache
    with _workflow_graph_lock:
        if _workflow_graph_cache is not None:
            return _workflow_graph_cache

    supervisor_on = os.environ.get("DIGI_SUPERVISOR", "").strip().lower() in ("1", "true", "yes")
    research_sg = build_research_subgraph()
    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    if supervisor_on:
        builder.add_node("supervisor", supervisor_node)
    builder.add_node("research", research_sg)
    builder.add_node("validate_strategy", strategy_validator_node)
    builder.add_node("backtest", backtest_node)
    builder.add_node("optimize", optimize_node)
    if supervisor_on:
        builder.add_edge(START, "supervisor")
        builder.add_conditional_edges("supervisor", _route_after_supervisor)
    else:
        builder.add_edge(START, "research")
    builder.add_conditional_edges("research", _route_after_research)
    builder.add_conditional_edges("validate_strategy", _route_after_validate)
    builder.add_conditional_edges("backtest", _route_after_backtest)
    builder.add_edge("optimize", END)

    checkpointer = get_checkpointer()
    store = get_store()
    interrupt_after: list[str] | None = None
    if (os.environ.get("DIGI_INTERRUPT_AFTER_RESEARCH", "").strip().lower()) in (
        "1",
        "true",
        "yes",
    ):
        # Interrupt after the research subgraph completes (outer node name is still "research").
        interrupt_after = ["research"]
    compiled = builder.compile(
        checkpointer=checkpointer, store=store, interrupt_after=interrupt_after
    )
    with _workflow_graph_lock:
        _workflow_graph_cache = compiled
    return compiled
