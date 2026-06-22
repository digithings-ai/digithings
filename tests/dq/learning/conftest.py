"""Learning-loop test collection gate.

``beliefs_distillation`` wires optional Hermes phases via digigraph; graph and
chain tests import the same stack. The standard ``digiquant-test`` CI job
installs only ``digiquant[dev]``, so digigraph runtime deps (e.g. ``openai``)
are absent — collecting these tests there would error out.

Full coverage runs in ``atlas-graph-ci.yml`` after install-workspace.sh.
"""

from __future__ import annotations


def _digigraph_importable() -> bool:
    try:
        import digigraph.graph.pipeline_builder  # noqa: F401
    except ImportError:
        return False
    return True


if not _digigraph_importable():
    collect_ignore_glob = ["test_*.py"]
