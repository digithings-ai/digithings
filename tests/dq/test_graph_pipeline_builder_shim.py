"""REM-059: digiquant.hermes.pipeline_builder re-exports DigiGraph builder."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_hermes_pipeline_builder_shim_exports() -> None:
    from digiquant.hermes import pipeline_builder as shim

    assert shim.NodeSpec is not None
    assert shim.PipelinePhase is not None
    assert callable(shim.build_pipeline)
