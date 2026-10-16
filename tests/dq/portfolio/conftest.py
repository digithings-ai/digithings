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

import logging

import pytest


@pytest.fixture(autouse=True)
def _restore_root_logger():
    """``chain.cli_main`` configures process-wide logging; keep that inside the test.

    ``_configure_cli_logging`` calls ``logging.basicConfig``, which sets the root
    level and installs a handler. That is right for a CLI entry point and wrong to
    leak into every later test, where it changes which records ``caplog`` can see.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        yield
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)


def _digigraph_importable() -> bool:
    try:
        import digigraph.graph.pipeline_builder  # noqa: F401
    except ImportError:
        return False
    return True


if not _digigraph_importable():
    collect_ignore_glob = ["test_*.py"]
