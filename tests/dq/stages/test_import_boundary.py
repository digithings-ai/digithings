from __future__ import annotations

from pathlib import Path

import pytest
from digiquant.stages.import_boundary import cross_stage_imports

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3] / "digiquant" / "src" / "digiquant"
_ALLOW = Path(__file__).resolve().parent / "fixtures" / "stage_import_allowlist.txt"


def test_cross_stage_imports_match_allowlist() -> None:
    expected = [line for line in _ALLOW.read_text(encoding="utf-8").splitlines() if line]
    assert cross_stage_imports(_ROOT) == expected
