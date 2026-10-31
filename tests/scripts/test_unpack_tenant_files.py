"""The container unpacker for the KV tenant-files bundle (stack src/tenant-files.ts)."""

from __future__ import annotations

import base64
import gzip
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "apps/digithings-stack-cloudflare/container/unpack_tenant_files.py"
)
_spec = importlib.util.spec_from_file_location("unpack_tenant_files", _SCRIPT)
assert _spec and _spec.loader
mod: Any = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _env(files: Any, chunk: int = 7) -> dict[str, str]:
    b64 = base64.b64encode(gzip.compress(json.dumps(files).encode())).decode()
    parts = [b64[i : i + chunk] for i in range(0, len(b64), chunk)]
    env = {f"DIGI_TENANT_FILES_{i}": p for i, p in enumerate(parts)}
    env["DIGI_TENANT_FILES_PARTS"] = str(len(parts))
    return env


def test_writes_site_graphs_and_page_corpora(tmp_path: Path) -> None:
    files = {"sites/acme.md": "site map", "pages/acme/about.md": "---\nurl: x\n---\nhi"}
    assert mod.unpack(_env(files, chunk=200), tmp_path) == (2, 0)
    assert (tmp_path / "sites/acme.md").read_text() == "site map"
    assert (tmp_path / "pages/acme/about.md").read_text().endswith("hi")


@pytest.mark.parametrize(
    "rel",
    [
        "../escape.md",
        "/etc/passwd",
        "sites/../x.md",
        "sites/acme.txt",
        "pages/acme/../../x.md",
        "pages/acme/sub/dir.md",
        "other/acme.md",
        "sites/Acme.md",
    ],
)
def test_refuses_any_other_path(tmp_path: Path, rel: str) -> None:
    root = tmp_path / "root"
    assert mod.unpack(_env({rel: "x"}), root) == (0, 1)
    assert not any(tmp_path.rglob("x.md")) and not (tmp_path / "escape.md").exists()


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"DIGI_TENANT_FILES_PARTS": "x"},
        {"DIGI_TENANT_FILES_PARTS": "1", "DIGI_TENANT_FILES_0": "not base64!"},
        {
            "DIGI_TENANT_FILES_PARTS": "1",
            "DIGI_TENANT_FILES_0": base64.b64encode(b"plain").decode(),
        },
        {"DIGI_TENANT_FILES_PARTS": "999"},
    ],
)
def test_a_bad_bundle_writes_nothing(tmp_path: Path, env: dict[str, str]) -> None:
    root = tmp_path / "root"
    assert mod.unpack(env, root) == (0, 0)
    assert not root.exists()


def test_main_never_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_TENANT_FILES_PARTS", "1")
    monkeypatch.setenv("DIGI_TENANT_FILES_0", "!!")
    monkeypatch.setattr("sys.argv", ["x", str(tmp_path)])
    assert mod.main() == 0
