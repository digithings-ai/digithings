"""Unit tests for scripts/probe_gloomberb_macro_panel.py (#4794, PR 1).

The probe records, per panel id, whether anonymous ``econ_series`` serves a
page. The suite is offline: ``classify`` is pure over an injected fake client
and no test spawns a process or touches the network.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from digiquant.data.prices.gloomberb_macro import DROPPED_SERIES_IDS, KEPT_SERIES_IDS

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_SCRIPT = REPO_ROOT / "scripts" / "probe_gloomberb_macro_panel.py"


def _load_probe() -> Any:
    spec = importlib.util.spec_from_file_location("probe_gloomberb_macro_panel", PROBE_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["probe_gloomberb_macro_panel"] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()


class FakeProbeClient:
    """Serves one observation per id in ``ok_ids``, an empty page otherwise."""

    def __init__(self, ok_ids: set[str]) -> None:
        self._ok_ids = ok_ids
        self.calls: list[Any] = []

    def econ_series(self, request: Any) -> Any:
        self.calls.append(request)
        series_id = request.series_id
        if series_id in self._ok_ids:
            observations = [{"date": "2026-09-23", "value": 1.0}]
        else:
            observations = []
        return SimpleNamespace(data=SimpleNamespace(observations=observations))


def test_probe_exits_0_when_split_matches() -> None:
    result = probe.classify(FakeProbeClient(set(KEPT_SERIES_IDS)))
    assert result.exit_code == 0
    by_id = {row.series_id: row for row in result.series}
    assert by_id["DGS10"].status == "ok"
    assert by_id["DTWEXBGS"].status == "empty"


def test_probe_exits_2_when_a_kept_id_is_empty() -> None:
    ok_ids = set(KEPT_SERIES_IDS) - {"DGS10"}
    result = probe.classify(FakeProbeClient(ok_ids))
    assert result.exit_code == 2
    by_id = {row.series_id: row for row in result.series}
    assert by_id["DGS10"].status == "empty"
    assert DROPPED_SERIES_IDS.isdisjoint(ok_ids)
