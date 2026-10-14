"""Pin the packaging excludes docs/DEPLOYMENT.md already claims.

``make package`` / ``scripts/package.sh`` is a whole-tree tarball. ``projects/``
is confidential and the deployment doc says it is excluded. The script used to
omit that exclude, so a checkout that had client data would ship it.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "package.sh"


def test_package_excludes_projects_directory() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "--exclude='projects'" in text
