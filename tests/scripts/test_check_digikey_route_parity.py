"""Tests for the digikey route manifest (DIG-2914).

What these pin, and why each one is here:

* The committed manifest must match the live FastAPI source. A Workers port that
  is checked against a stale manifest is checked against nothing.
* The detector must fire on a removed route, an added route, and a changed auth
  class. A detector that finds nothing looks the same as a detector that is not
  wired up, so each case is a synthetic source file rather than only the real tree.
* The route census is asserted as an exact set. Without it, deleting a route from
  the Python service and regenerating the manifest would silently shrink the
  surface the Worker must reproduce.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_digikey_route_parity.py"
MANIFEST = REPO_ROOT / "config" / "digikey-route-manifest.json"

_spec = importlib.util.spec_from_file_location("check_digikey_route_parity", SCRIPT)
parity = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(parity)

EXPECTED_ROUTES = {
    ("GET", "/.well-known/jwks.json"),
    ("GET", "/health"),
    ("GET", "/healthz"),
    ("POST", "/v1/admin/bff-sessions/revoke"),
    ("POST", "/v1/admin/keys"),
    ("POST", "/v1/admin/keys/{key_id}/revoke"),
    ("POST", "/v1/admin/licenses/{license_id}/revoke"),
    ("POST", "/v1/licenses/heartbeat"),
    ("POST", "/v1/oauth/token"),
}

SAMPLE_SOURCE = '''
from fastapi import Depends, FastAPI, Request

app = FastAPI()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/v1/admin/keys", response_model=AdminIssueResponse, summary="Issue API key")
def admin_issue_key(body: AdminIssueBody, request: Request) -> AdminIssueResponse:
    _require_admin(request)


@app.post("/v1/oauth/token", response_model=TokenResponse)
def oauth_token(body: TokenRequest, request: Request) -> TokenResponse:
    verify_secret(body.key, row.key_hash)
'''


def _source(tmp_path: Path, text: str = SAMPLE_SOURCE) -> Path:
    path = tmp_path / "server.py"
    path.write_text(text, encoding="utf-8")
    return path


def _manifest(tmp_path: Path, source: Path) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(parity.build_manifest(source, path)), encoding="utf-8")
    return path


def _run(source: Path, manifest: Path) -> int:
    return parity.main(["--source", str(source), "--manifest", str(manifest)])


def test_committed_manifest_matches_source() -> None:
    assert parity.main([]) == 0


def test_manifest_census_is_exact() -> None:
    routes = json.loads(MANIFEST.read_text(encoding="utf-8"))["routes"]
    assert {(r["method"], r["path"]) for r in routes} == EXPECTED_ROUTES


def test_detects_removed_route(tmp_path: Path) -> None:
    source = _source(tmp_path)
    manifest = _manifest(tmp_path, source)
    _source(tmp_path, SAMPLE_SOURCE.replace('@app.get("/health")', '@app.get("/healthz")'))
    assert _run(source, manifest) == 1


def test_detects_added_route(tmp_path: Path) -> None:
    source = _source(tmp_path)
    manifest = _manifest(tmp_path, source)
    added = '\n\n@app.get("/metrics")\ndef metrics() -> dict:\n    return {}\n'
    _source(tmp_path, SAMPLE_SOURCE + added)
    assert _run(source, manifest) == 1


def test_detects_changed_auth(tmp_path: Path) -> None:
    source = _source(tmp_path)
    manifest_path = _manifest(tmp_path, source)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for route in manifest["routes"]:
        if route["path"] == "/health":
            route["auth"] = "admin"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert _run(source, manifest_path) == 1


def test_update_rewrites_manifest(tmp_path: Path) -> None:
    source = _source(tmp_path)
    manifest = tmp_path / "manifest.json"
    assert parity.main(["--source", str(source), "--manifest", str(manifest), "--update"]) == 0
    written = json.loads(manifest.read_text(encoding="utf-8"))
    assert {(r["method"], r["path"]) for r in written["routes"]} == {
        ("GET", "/health"),
        ("POST", "/v1/admin/keys"),
        ("POST", "/v1/oauth/token"),
    }
    assert _run(source, manifest) == 0


def test_missing_manifest_is_an_error_not_a_pass(tmp_path: Path) -> None:
    source = _source(tmp_path)
    assert _run(source, tmp_path / "nope.json") == 2
