"""PATH lookup does not invoke a shell."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.probe import lookup_on_path

pytestmark = pytest.mark.unit


def test_lookup_finds_executable(tmp_path: Path) -> None:
    binary = tmp_path / "whisper-cli"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    assert lookup_on_path("whisper-cli", str(tmp_path)) == str(binary)


def test_lookup_skips_non_executable(tmp_path: Path) -> None:
    binary = tmp_path / "piper"
    binary.write_text("not executable\n", encoding="utf-8")
    assert lookup_on_path("piper", str(tmp_path)) is None


def test_lookup_empty_path() -> None:
    assert lookup_on_path("sox", None) is None
    assert lookup_on_path("sox", "") is None
