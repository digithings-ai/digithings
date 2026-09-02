"""Where the detailed telemetry flush sits in the chain's exit path (#1979, Task 1.5).

Three orderings carry the whole task, and each of them fails silently rather than loudly:

* Flush **before** ``_usage.reset()``. Reset clears the buffers, so a flush after it inserts
  nothing while returning a result that reads as success.
* Flush **before** ``write_row``. That is what makes the two writes independent in both
  directions without modifying the aggregate path.
* Flush **inside** the ``finally``, so a run that dies still persists what it bought.
"""

from __future__ import annotations

from datetime import date
from typing import Any  # score:allow untyped any — scored-lint: opaque ChainDeps/monkeypatch args

import pytest
from digiquant.olympus.atlas.graph import AtlasInput
from digiquant.olympus.hermes import chain as chain_mod

from digigraph import usage as _usage

pytestmark = pytest.mark.unit


def _deps(client: Any = None, run_id: str = "gha-1979") -> Any:
    return chain_mod.ChainDeps(
        atlas=None,
        hermes=None,
        diagnostics=chain_mod.DiagnosticsDeps(client=client, run_id=run_id, attempt=2),
    )


def _beliefs_input() -> AtlasInput:
    # The shortest path through run_atlas_then_hermes that still enters the try/finally.
    # `daily` is the only cadence AtlasResearchState accepts.
    return AtlasInput(cadence="daily", run_date=date(2026, 8, 7), refresh_scope="beliefs")


class Trace(list):  # type: ignore[type-arg]
    """The exit-path call order, plus whatever kwargs the flush was handed."""

    flush_kwargs: dict[str, Any]


@pytest.fixture
def trace(monkeypatch: pytest.MonkeyPatch) -> Trace:
    """Record the exit-path call order, keeping `_usage.reset` real so buffers truly clear."""
    order = Trace()
    order.flush_kwargs = {}
    real_reset = _usage.reset

    def _flush(*_a: Any, **kwargs: Any) -> Any:
        order.append("flush")
        order.flush_kwargs = kwargs
        return None

    def _write_row(*_a: Any, **_k: Any) -> Any:
        order.append("write_row")
        return None

    def _reset() -> None:
        order.append("reset")
        real_reset()

    monkeypatch.setattr(chain_mod._provider_telemetry, "flush_run_telemetry", _flush)
    monkeypatch.setattr(chain_mod._diagnostics, "write_row", _write_row)
    monkeypatch.setattr(chain_mod._usage, "reset", _reset)
    return order


def _emit_a_node_run(*_a: Any, **_k: Any) -> None:
    """Stand in for a graph node: opens a real node scope, so a real record is buffered."""
    with _usage.node_run_scope("test/beliefs-node", fanout_key="NVDA"):
        pass


def test_a_successful_run_flushes_the_detailed_ledger_once(
    monkeypatch: pytest.MonkeyPatch, trace: Trace
) -> None:
    monkeypatch.setattr(chain_mod, "_run_beliefs_fold", lambda *a, **k: None)

    chain_mod.run_atlas_then_hermes(atlas_input=_beliefs_input(), deps=_deps())

    assert trace.count("flush") == 1


def test_the_flush_precedes_both_the_aggregate_write_and_the_buffer_reset(
    monkeypatch: pytest.MonkeyPatch, trace: Trace
) -> None:
    monkeypatch.setattr(chain_mod, "_run_beliefs_fold", lambda *a, **k: None)

    chain_mod.run_atlas_then_hermes(atlas_input=_beliefs_input(), deps=_deps())

    assert trace == ["flush", "write_row", "reset"]


def test_the_flush_sees_the_records_the_run_actually_buffered(
    monkeypatch: pytest.MonkeyPatch, trace: Trace
) -> None:
    """The direct proof that the flush is not ordered after `reset()`: reset clears `_NODE_RUNS`,
    so a flush behind it would be handed an empty list and report a clean, empty success."""
    monkeypatch.setattr(chain_mod, "_run_beliefs_fold", _emit_a_node_run)

    chain_mod.run_atlas_then_hermes(atlas_input=_beliefs_input(), deps=_deps())

    kwargs = trace.flush_kwargs
    assert kwargs["run_id"] == "gha-1979"
    assert kwargs["attempt"] == 2, "the flush key must match the diagnostics conflict key"
    node_runs = kwargs["node_runs"]
    assert len(node_runs) == 1
    assert node_runs[0].node_name == "test/beliefs-node"
    assert node_runs[0].fanout_key == "NVDA"
    # And the buffer really is cleared afterwards, so the assertion above proves ordering.
    assert _usage.node_runs_snapshot() == []


def test_a_run_that_raises_still_flushes_and_reraises_unchanged(
    monkeypatch: pytest.MonkeyPatch, trace: Trace
) -> None:
    """chain.py's `except BaseException` records the crash and re-raises; the finally must
    still persist what the run bought before it died."""
    boom = RuntimeError("terminal")

    def _explode(*_a: Any, **_k: Any) -> None:
        _emit_a_node_run()
        raise boom

    monkeypatch.setattr(chain_mod, "_run_beliefs_fold", _explode)

    with pytest.raises(RuntimeError) as caught:
        chain_mod.run_atlas_then_hermes(atlas_input=_beliefs_input(), deps=_deps())

    assert caught.value is boom, "telemetry must not substitute its own exception"
    assert trace.count("flush") == 1
    assert len(trace.flush_kwargs["node_runs"]) == 1


def test_a_terminating_exception_still_flushes(
    monkeypatch: pytest.MonkeyPatch, trace: Trace
) -> None:
    """KeyboardInterrupt is a BaseException — the class `except Exception` would miss."""

    def _explode(*_a: Any, **_k: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(chain_mod, "_run_beliefs_fold", _explode)

    with pytest.raises(KeyboardInterrupt):
        chain_mod.run_atlas_then_hermes(atlas_input=_beliefs_input(), deps=_deps())

    assert trace == ["flush", "write_row", "reset"]


def test_a_detailed_flush_failure_leaves_the_aggregate_row_written(
    monkeypatch: pytest.MonkeyPatch, trace: Trace
) -> None:
    """flush_run_telemetry does not raise; this proves the call site is safe even if it did."""

    def _explode(*_a: Any, **_k: Any) -> None:
        trace.append("flush")
        raise RuntimeError("telemetry outage")

    monkeypatch.setattr(chain_mod._provider_telemetry, "flush_run_telemetry", _explode)
    monkeypatch.setattr(chain_mod, "_run_beliefs_fold", lambda *a, **k: None)

    # The run completes normally — a telemetry failure is not a run failure.
    chain_mod.run_atlas_then_hermes(atlas_input=_beliefs_input(), deps=_deps())

    assert trace == ["flush", "write_row", "reset"]


def test_an_aggregate_failure_leaves_the_detailed_flush_done(
    monkeypatch: pytest.MonkeyPatch, trace: Trace
) -> None:
    """`write_row` is fail-soft for its upsert but calls `summarize_run` outside that `try`.
    Ordering the detailed flush first is what keeps that pre-existing raise path from taking
    the detailed records with it."""

    def _explode(*_a: Any, **_k: Any) -> None:
        trace.append("write_row")
        raise RuntimeError("summarize_run blew up")

    monkeypatch.setattr(chain_mod._diagnostics, "write_row", _explode)
    monkeypatch.setattr(chain_mod, "_run_beliefs_fold", _emit_a_node_run)

    with pytest.raises(RuntimeError):
        chain_mod.run_atlas_then_hermes(atlas_input=_beliefs_input(), deps=_deps())

    assert trace.index("flush") < trace.index("write_row")
    assert len(trace.flush_kwargs["node_runs"]) == 1


def test_without_diagnostics_wiring_nothing_is_flushed_and_the_absence_is_logged(
    monkeypatch: pytest.MonkeyPatch, trace: Trace, caplog: pytest.LogCaptureFixture
) -> None:
    """A run with no diagnostics deps has no run identifier, so `node_run_scope` never opens and
    no node runs or logical calls are produced *at the source* — not merely left unflushed."""
    monkeypatch.setattr(chain_mod, "_run_beliefs_fold", _emit_a_node_run)
    deps = chain_mod.ChainDeps(atlas=None, hermes=None)

    with caplog.at_level("INFO", logger=chain_mod._logger.name):
        chain_mod.run_atlas_then_hermes(atlas_input=_beliefs_input(), deps=deps)

    assert "flush" not in trace
    assert _usage.node_runs_snapshot() == []
    assert any("no diagnostics wiring" in record.message for record in caplog.records), (
        "a counted, logged condition — never a silent no-op"
    )
