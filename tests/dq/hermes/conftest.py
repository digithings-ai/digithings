"""Hermes test collection gate.

The Hermes sub-package imports ``digigraph.graph.pipeline_builder`` (and the
research-agent driver) which in turn pulls ``openai``. The standard
``digiquant-test`` CI job installs only ``digiquant[dev]``, so digigraph's
runtime deps are absent — collecting the Hermes tests there would error out.

Mirrors :mod:`tests.dq.atlas.conftest`. The full Hermes test set runs in
``test-atlas-graph.yml`` (extended with Hermes paths in #476) where
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
