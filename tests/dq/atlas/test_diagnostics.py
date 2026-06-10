from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

pytest.importorskip("openai")  # diagnostics imports digigraph.usage chain

from digigraph import usage  # noqa: E402
from digiquant.olympus.atlas import diagnostics  # noqa: E402
from digiquant.olympus.atlas.state import AtlasResearchState  # noqa: E402
from digiquant.olympus.atlas.segments import SegmentReport  # noqa: E402
from digiquant.olympus.atlas.state import Carried, SegmentPayload, SegmentSlot  # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
    usage.reset()
    yield
    usage.reset()


def _seg_slot(slug: str) -> SegmentSlot:
    return SegmentSlot(
        payload=SegmentPayload(
            segment=slug,
            body=SegmentReport(
                segment=slug, date=date(2026, 6, 10), bias="neutral", headline="h"
            ).model_dump(mode="json"),
            as_of=date(2026, 6, 10),
        )
    )


@pytest.mark.unit
def test_build_row_aggregates_usage_and_segments():
    usage.start()
    usage.record(kind="chat", model="xai/grok-4.3", prompt_tokens=1000, completion_tokens=400)
    usage.record(kind="web_search", model="xai/grok-4.3", sources=8, ok=True)
    usage.record(kind="x_search", model="xai/grok-4.3", sources=16, ok=True)

    state = AtlasResearchState(run_type="baseline", run_date=date(2026, 6, 10))
    state.phase1_outputs = {"alt-sentiment-news": _seg_slot("alt-sentiment-news")}
    state.phase2_outputs = {
        "inst-hedge-fund-intel": SegmentSlot(
            payload=Carried(baseline_date=date(2026, 6, 9), reason="unchanged")
        )
    }

    row = diagnostics.build_row(
        run_id="run-123",
        run_type="baseline",
        run_date=date(2026, 6, 10),
        status="success",
        started_at=datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 10, 12, 5, 0, tzinfo=timezone.utc),
        state=state,
    )
    assert row["run_id"] == "run-123"
    assert row["llm_calls"] == 1
    assert row["total_tokens"] == 1400
    assert row["search_calls"] == 2
    assert row["sources_used"] == 24
    assert row["duration_s"] == 300.0
    assert row["segments_ok"] == 1
    assert row["segments_carried"] == 1
    assert row["segments_total"] == 2
    assert row["est_cost_usd"] >= 0
    assert "by_kind" in row["breakdown"]


@pytest.mark.unit
def test_build_row_failure_carries_error_and_status():
    usage.start()
    row = diagnostics.build_row(
        run_id="r2",
        run_type="delta",
        run_date=date(2026, 6, 10),
        status="failure",
        started_at=datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 10, 12, 1, 0, tzinfo=timezone.utc),
        state=None,
        error="boom 401",
    )
    assert row["status"] == "failure"
    assert "boom 401" in row["error_summary"]
    assert row["segments_total"] == 0


class _FakeTable:
    def __init__(self, sink):
        self._sink = sink

    def upsert(self, row, on_conflict=None):
        self._sink["row"] = row
        self._sink["on_conflict"] = on_conflict
        return self

    def execute(self):
        return type("R", (), {"data": [self._sink["row"]]})


class _FakeClient:
    def __init__(self, sink, raise_=False):
        self._sink = sink
        self._raise = raise_

    def table(self, name):
        self._sink["table"] = name
        if self._raise:
            raise RuntimeError("relation does not exist")
        return _FakeTable(self._sink)


@pytest.mark.unit
def test_write_row_upserts_on_run_id():
    sink: dict = {}
    ok = diagnostics.write_row(_FakeClient(sink), {"run_id": "r1", "status": "success"})
    assert ok is True
    assert sink["table"] == "atlas_run_diagnostics"
    assert sink["on_conflict"] == "run_id"


@pytest.mark.unit
def test_write_row_fails_soft_on_error():
    # Missing table / transient error must never raise.
    assert diagnostics.write_row(_FakeClient({}, raise_=True), {"run_id": "r1"}) is False
