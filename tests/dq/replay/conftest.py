"""Replay test collection gates.

``test_walk_forward`` builds on ``learning.outcome_models``; importing that
package executes ``learning/__init__.py``, which wires beliefs distillation
through digigraph. The standard ``digiquant-test`` CI job installs only
``digiquant[dev]``, so digigraph runtime deps (e.g. ``openai``) are absent.

Full coverage runs in ``test-atlas-graph.yml`` after ``uv sync --all-packages``.
"""

from __future__ import annotations


def _digigraph_importable() -> bool:
    try:
        import digigraph.graph.pipeline_builder  # noqa: F401
    except ImportError:
        return False
    return True


if not _digigraph_importable():
    collect_ignore = ["test_walk_forward.py"]
