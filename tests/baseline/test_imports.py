"""Baseline import tests — verify all public packages can be imported.

These tests have no external dependencies (no network, no Docker, no DB).
They exist to catch import-time breakage (missing deps, circular imports,
syntax errors) before any other test runs.
"""

from __future__ import annotations

import pytest


@pytest.mark.baseline
def test_digibase_imports() -> None:
    import digibase  # noqa: F401


@pytest.mark.baseline
def test_digikey_imports() -> None:
    import digikey  # noqa: F401


@pytest.mark.baseline
def test_digismith_imports() -> None:
    import digismith  # noqa: F401


@pytest.mark.baseline
def test_digiclaw_imports() -> None:
    import digiclaw  # noqa: F401


@pytest.mark.baseline
def test_digiquant_imports() -> None:
    import digiquant  # noqa: F401


@pytest.mark.baseline
def test_digisearch_imports() -> None:
    import digisearch  # noqa: F401


@pytest.mark.baseline
def test_digigraph_imports() -> None:
    import digigraph  # noqa: F401
