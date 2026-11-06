"""The public runtime must not import Chroma or its client."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.unit
def test_server_import_does_not_load_chromadb() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    code = """
import sys
import digisearch.server
import digisearch.mcp_server
loaded = sorted(name for name in sys.modules if name == "chromadb" or name.startswith("chromadb."))
print(",".join(loaded))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "", (
        "public digisearch startup imported chromadb: " + result.stdout.strip()
    )
