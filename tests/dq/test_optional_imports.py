"""digiquant._optional: absent modules yield None, broken ones still raise (#6751)."""

from __future__ import annotations

import sys

import pytest
from digiquant._optional import has_module, optional_attrs

pytestmark = pytest.mark.unit


def test_absent_module_yields_none_per_name():
    assert optional_attrs("digiquant.no_such_module", "a", "b") == (None, None)


def test_absent_parent_package_yields_none():
    assert optional_attrs("digiquant.no_such_pkg.child", "x") == (None,)
    assert has_module("digiquant.no_such_pkg.child") is False


def test_present_module_returns_attributes():
    (dumps,) = optional_attrs("json", "dumps")
    import json

    assert dumps is json.dumps
    assert has_module("json") is True


def test_installed_module_with_a_missing_dependency_still_raises(tmp_path, monkeypatch):
    pkg = tmp_path / "optpkg_broken"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("import optpkg_dependency_that_is_absent\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "optpkg_broken", raising=False)
    with pytest.raises(ModuleNotFoundError):
        optional_attrs("optpkg_broken", "anything")
