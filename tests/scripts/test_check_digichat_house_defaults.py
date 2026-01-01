"""The house-defaults drift check passes on this tree."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPT = REPO / "scripts" / "check_digichat_house_defaults.py"

pytestmark = pytest.mark.unit


def test_house_defaults_match_the_tree() -> None:
    spec = importlib.util.spec_from_file_location("check_digichat_house_defaults", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0
