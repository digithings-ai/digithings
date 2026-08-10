"""Ensure authored digichat OpenAPI paths map to App Router route handlers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
OPENAPI = REPO / "docs" / "openapi" / "digichat.json"
API_ROOT = REPO / "frontend" / "digichat" / "src" / "app" / "api"


def _route_file_for(path: str) -> Path:
    """Map OpenAPI path to Next.js App Router file.

    /api/health -> api/health/route.ts
    /api/conversations/{id} -> api/conversations/[id]/route.ts
    /api/auth/{nextauth} -> api/auth/[...nextauth]/route.ts
    """
    assert path.startswith("/api/"), path
    parts = path[len("/api/") :].split("/")
    mapped: list[str] = []
    for p in parts:
        if p.startswith("{") and p.endswith("}"):
            name = p[1:-1]
            if name == "nextauth":
                mapped.append("[...nextauth]")
            else:
                mapped.append(f"[{name}]")
        else:
            mapped.append(p)
    return API_ROOT.joinpath(*mapped, "route.ts")


@pytest.mark.unit
def test_digichat_openapi_paths_exist_on_disk() -> None:
    assert OPENAPI.is_file(), f"missing {OPENAPI}"
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    paths = spec.get("paths") or {}
    assert paths, "digichat OpenAPI has no paths"
    missing: list[str] = []
    for p in paths:
        route = _route_file_for(p)
        if not route.is_file():
            missing.append(f"{p} → {route.relative_to(REPO)}")
    assert not missing, "OpenAPI paths without route handlers:\n" + "\n".join(missing)
