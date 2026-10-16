"""Regression tests: unused connector base DTOs stay removed."""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit


def test_connector_base_stubs_are_not_exported() -> None:
    import digibase.connectors as connectors

    assert not hasattr(connectors, "ConnectorPayload")
    assert not hasattr(connectors, "ConnectorResult")


def test_connector_base_module_is_gone() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("digibase.connectors.base")


def test_connectors_package_still_imports() -> None:
    importlib.import_module("digibase.connectors")
