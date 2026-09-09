"""Declarative pipeline builder for LangGraph sub-graphs.

A sub-graph like digiquant research (#176) is a sequence of phases; each phase
has one or more nodes that may run in parallel, and every phase fully completes
before the next begins. Instead of open-coding the edge plumbing per sub-graph,
callers declare a ``list[PipelinePhase]`` and this builder compiles it into a
``StateGraph``.

Design:
- Each ``NodeSpec.run`` is a function that takes the state model and returns a
  dict of field updates — the standard LangGraph node signature.
- Parallel nodes in a phase fan out from a synthetic barrier node and fan back
  in at the next barrier. This keeps LangGraph's default last-writer-wins
  semantics safe: parallel nodes must write disjoint top-level fields (enforced
  by the caller, not by the builder — the builder's job is topology, not
  reducer policy).
"""

from __future__ import annotations

import functools
import inspect
import logging
from dataclasses import dataclass

# The noqa below is read by repo-local `scripts/score.py` (not ruff) — that
# gate flags unscoped `Any` imports. LangGraph node update dicts are
# legitimately heterogeneous, so `Any` here is intentional.
from typing import Any, Callable, Sequence  # score:allow untyped any — scored-lint suppression

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from digigraph.usage import node_run_scope

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NodeSpec:
    """A single node within a phase."""

    name: str
    run: Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class PipelinePhase:
    """A phase: one or more nodes that run in parallel; next phase blocks on all."""

    name: str
    nodes: Sequence[NodeSpec]


@dataclass(frozen=True)
class FanOutPhase:
    """A phase that maps a runtime-computed item list to parallel workers via LangGraph ``Send``.

    Unlike :class:`PipelinePhase` — whose node set is fixed at build time — a fan-out phase
    discovers its items at *run* time from the live state (e.g. the portfolio focus roster that H4
    computes mid-run). The builder wires a map-reduce::

        prev_exit --(conditional: one Send per item)--> worker (parallel) --> barrier --> next

    Each ``Send`` hands the worker a copy of the live state with one item injected via
    ``with_item(state, item)``; the worker reads it back and returns updates that the *state
    model's reducers* merge across the parallel invocations (so every field a worker writes
    MUST be ``Annotated`` with a merge reducer, exactly as for a parallel ``PipelinePhase``).
    An empty item list short-circuits straight to the barrier so the graph never stalls.

    Attributes:
        name: Phase name (unique across the pipeline).
        worker: The single per-item node; registered once, invoked once per item in parallel.
        items: ``state -> sequence`` of items to fan out over, evaluated at run time.
        with_item: ``(state, item) -> state`` returning a state copy that carries ``item`` for
            the worker to read (typically ``state.model_copy(update={...})``).
        item_key: Optional ``state -> label`` that reads back the per-``Send`` cursor
            ``with_item`` injected. Used only as the telemetry fan-out discriminator
            (``NodeRunRecord.fanout_key``); it never affects dispatch, routing, or reducers,
            and a failure or blank result leaves the discriminator absent.
    """

    name: str
    worker: NodeSpec
    items: Callable[[Any], Sequence[Any]]
    with_item: Callable[[Any, Any], Any]
    item_key: Callable[[Any], Any] | None = None

    @property
    def nodes(self) -> tuple[NodeSpec, ...]:
        """Expose the worker as a 1-tuple so name validation/registration treat it uniformly."""
        return (self.worker,)


def _fanout_key(key_of: Callable[[Any], Any] | None, state: Any) -> str | None:
    """Best-effort per-``Send`` discriminator. A telemetry label must never change a node."""
    if key_of is None:
        return None
    try:
        value = key_of(state)
    except Exception:
        # Warning, not debug: a broken extractor is a wiring bug and should be visible. It
        # must not be fatal — telemetry cannot change the exceptions a node raises.
        logger.warning("fan-out telemetry key extraction failed", exc_info=True)
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _instrumented(
    node_name: str,
    run: Callable[..., dict[str, Any]],
    key_of: Callable[[Any], Any] | None,
) -> Callable[..., dict[str, Any]]:
    """Wrap one node body in its run/node telemetry scope without changing its contract.

    ``functools.wraps`` plus ``*args/**kwargs`` is mandatory, not stylistic: LangGraph decides
    what to inject from ``inspect.signature(func).parameters``, matched by parameter name and
    annotation, and ``inspect.signature`` follows ``__wrapped__``. A ``(state)``-only wrapper
    breaks any node declaring ``config``/``writer``/``store``/``runtime``. ``wraps`` also
    preserves ``__name__``, which LangGraph reads for the trace name.

    A coroutine node needs a coroutine wrapper. ``functools.wraps`` copies the inner signature,
    so a sync wrapper around an ``async def`` looks synchronous to LangGraph while returning an
    un-awaited coroutine: the node fails with ``InvalidUpdateError: Expected dict, got
    <coroutine>`` instead of being routed to the async path. No node registered here is async
    today and nothing calls ``ainvoke``, so this is latent — but a sync-only wrapper would make
    an async node permanently unroutable rather than merely unused.
    """
    if inspect.iscoroutinefunction(run):

        @functools.wraps(run)
        async def _awrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
            state = args[0] if args else kwargs.get("state")
            with node_run_scope(node_name, fanout_key=_fanout_key(key_of, state)):
                return await run(*args, **kwargs)

        return _awrapped

    @functools.wraps(run)
    def _wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        state = args[0] if args else kwargs.get("state")
        with node_run_scope(node_name, fanout_key=_fanout_key(key_of, state)):
            return run(*args, **kwargs)

    return _wrapped


def build_pipeline(
    state_cls: type,
    phases: Sequence[PipelinePhase | FanOutPhase],
    *,
    checkpointer: Any = None,
) -> Any:
    """Compile ``phases`` into a LangGraph ``StateGraph`` over ``state_cls``.

    Returns the compiled graph (ready to ``invoke``). When ``checkpointer`` is
    provided, the graph is compiled with it so per-node state is persisted and a
    run can resume (``invoke(None, {"configurable": {"thread_id": ...}})``) — each
    segment/specialist node is a checkpoint boundary (#665). Without one, the graph
    compiles plainly and ``invoke`` needs no ``thread_id`` (back-compat).

    Rules:
    - Phases run sequentially. All nodes in phase N complete before phase N+1 starts.
    - Nodes within one phase run in parallel (LangGraph fan-out from barrier).
    - Single-node phases are wired directly — no synthetic barrier.
    - Node names must be unique across the whole pipeline; phase names must be
      unique. Raises ``ValueError`` on conflict so typos fail loudly at build time.
    """
    if not phases:
        raise ValueError("build_pipeline: at least one phase is required")

    # `__barrier__` is reserved for the synthetic fan-in nodes this builder
    # generates. Reject user-supplied names with that prefix so we never collide.
    _BARRIER_PREFIX = "__barrier__"

    seen_phase: set[str] = set()
    seen_node: set[str] = set()
    for phase in phases:
        if phase.name.startswith(_BARRIER_PREFIX):
            raise ValueError(
                f"phase name {phase.name!r} starts with reserved prefix {_BARRIER_PREFIX!r}"
            )
        if phase.name in seen_phase:
            raise ValueError(f"duplicate phase name: {phase.name!r}")
        seen_phase.add(phase.name)
        if not phase.nodes:
            raise ValueError(f"phase {phase.name!r} must declare at least one node")
        for node in phase.nodes:
            if node.name.startswith(_BARRIER_PREFIX):
                raise ValueError(
                    f"node name {node.name!r} starts with reserved prefix {_BARRIER_PREFIX!r}"
                )
            if node.name in seen_node:
                raise ValueError(f"duplicate node name across pipeline: {node.name!r}")
            seen_node.add(node.name)

    graph: StateGraph = StateGraph(state_cls)

    # Register every runnable node inside its telemetry node scope. The wrapper is
    # signature-transparent (`functools.wraps` + `*args/**kwargs`), so LangGraph's
    # signature-driven config/writer/store/previous/runtime/error injection still sees the
    # node's own parameters. Synthetic barriers below are intentionally NOT wrapped: `_noop`
    # runs no user code and makes no provider calls, so it emits no node record —
    # reconciliation counts real node executions, not compiled graph nodes.
    for phase in phases:
        key_of = phase.item_key if isinstance(phase, FanOutPhase) else None
        for node in phase.nodes:
            graph.add_node(node.name, _instrumented(node.name, node.run, key_of))

    # Synthetic barriers. A barrier is a no-op node that joins a fan-out and
    # launches the next fan-out. For single-node phases, the node itself acts
    # as its own entry + exit, so the barrier is skipped.
    def _noop(_state: Any) -> dict[str, Any]:
        return {}

    prev_exit: str = START
    for idx, phase in enumerate(phases):
        if isinstance(phase, FanOutPhase):
            # Map-reduce: prev_exit --(one Send per runtime item)--> worker (parallel) --> barrier.
            worker_name = phase.worker.name
            barrier_name = f"{_BARRIER_PREFIX}{idx}__{phase.name}"
            graph.add_node(barrier_name, _noop)

            def _dispatch(
                state: Any,
                _items: Callable[[Any], Sequence[Any]] = phase.items,
                _with_item: Callable[[Any, Any], Any] = phase.with_item,
                _worker: str = worker_name,
                _barrier: str = barrier_name,
            ) -> Any:
                items = list(_items(state))
                if not items:
                    return _barrier  # nothing to map → fall straight through to the join
                return [Send(_worker, _with_item(state, item)) for item in items]

            graph.add_conditional_edges(prev_exit, _dispatch, [worker_name, barrier_name])
            graph.add_edge(worker_name, barrier_name)
            prev_exit = barrier_name
            continue

        nodes = list(phase.nodes)
        if len(nodes) == 1:
            only = nodes[0].name
            if prev_exit == START:
                graph.add_edge(START, only)
            else:
                graph.add_edge(prev_exit, only)
            prev_exit = only
            continue

        # Multi-node phase: fan out from prev_exit to each node, fan in to a barrier.
        barrier_name = f"{_BARRIER_PREFIX}{idx}__{phase.name}"
        graph.add_node(barrier_name, _noop)
        for node in nodes:
            if prev_exit == START:
                graph.add_edge(START, node.name)
            else:
                graph.add_edge(prev_exit, node.name)
            graph.add_edge(node.name, barrier_name)
        prev_exit = barrier_name

    graph.add_edge(prev_exit, END)
    return graph.compile(checkpointer=checkpointer) if checkpointer is not None else graph.compile()
