"""portfolio test collection gate.

The portfolio sub-package imports ``digigraph.graph.pipeline_builder`` (and the
research-agent driver) which in turn pulls ``openai``. The standard
``digiquant-test`` CI job installs only ``digiquant[dev]``, so digigraph's
runtime deps are absent — collecting the portfolio tests there would error out.

Mirrors :mod:`tests.dq.research.conftest`. The full portfolio test set runs in
``test-research-graph.yml`` (extended with portfolio paths in #476) where
``install-workspace.sh`` has installed digigraph + its deps first.
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
