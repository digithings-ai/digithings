"""`build-manifest.mjs` must map route-group families and index the kit (#4225).

`pageFamily` read the first path segment under `app/`, so once the family pages
moved under `reference/app/(gallery)/<fam>/page.tsx` every page collapsed into
the `(gallery)` family — 5 families / 111 components instead of 15 / 106. A
next.js route group is organisational, not a family, so `(...)` segments must be
skipped (and the bare `app/(gallery)/page.tsx` falls back to `foundations`).

The vendored shadcn kit (`web/src/ui/*.tsx`) is importable only as the package
export `@digithings/web/ui`, never as `@/components/*`, so no reference page maps
it and it must be indexed directly from source, one row per file.

The script takes an output path as argv[2], so this test writes to a temp file
and never rewrites the committed `MANIFEST.json`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "cloudflare" / "digiweb" / "scripts" / "build-manifest.mjs"


@pytest.fixture(scope="module")
def manifest(tmp_path_factory: pytest.TempPathFactory) -> dict:
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    out = tmp_path_factory.mktemp("manifest") / "MANIFEST.json"
    subprocess.run(["node", str(SCRIPT), str(out)], cwd=REPO_ROOT, check=True)
    return json.loads(out.read_text(encoding="utf-8"))


def test_route_groups_are_not_families(manifest: dict) -> None:
    families = set(manifest["families"])
    assert not [f for f in families if f.startswith("(")], families
    # app/(gallery)/page.tsx → foundations; app/(gallery)/<fam>/ → <fam>.
    assert "foundations" in families
    assert "account" in families


def test_counts_match_the_index(manifest: dict) -> None:
    entries = [e for fam in manifest["families"].values() for e in fam]
    assert manifest["counts"]["components"] == len(entries)
    assert manifest["counts"]["families"] == len(manifest["families"])


def test_ui_kit_is_indexed_from_package_source(manifest: dict) -> None:
    ui = {e["id"]: e for e in manifest["families"]["ui"]}
    assert {"button", "card", "dialog", "input"} <= set(ui)
    assert ui["button"]["path"] == "web/src/ui/button.tsx"
    assert ui["button"]["name"] == "Button"
    # Test files under the source dir are not components.
    assert not [i for i in ui if i.endswith(".test")]
