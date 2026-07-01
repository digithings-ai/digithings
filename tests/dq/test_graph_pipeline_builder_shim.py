"""REM-059: digiquant.olympus.hermes.pipeline_builder re-exports DigiGraph builder."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _digigraph_importable() -> bool:
    try:
        import digigraph.graph.pipeline_builder  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(
    not _digigraph_importable(),
    reason="digigraph runtime deps not installed (CI digiquant-test job)",
)
def test_hermes_pipeline_builder_shim_exports() -> None:
    from digiquant.olympus.hermes import pipeline_builder as shim

    assert shim.NodeSpec is not None
    assert shim.PipelinePhase is not None
    assert callable(shim.build_pipeline)
