"""E2E loader test: DigiGraph resolves digiproject.yaml and surfaces it via /v1/status.

Self-contained via FastAPI TestClient — no running stack required, but marked `e2e`
per epic #3 so it runs under the e2e suite.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from digigraph.project_config import DigiProjectConfig
from digigraph.server import app
from tests.digi_test_jwt import auth_headers

TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "templates" / "project" / "digiproject.yaml"
)


@pytest.mark.e2e
def test_status_surfaces_template_digiproject_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copy the project template into a tmp dir, point DIGI_PROJECT_CONFIG at it, hit /v1/status.

    Assertions intentionally cover only the secret-free subset surfaced by the endpoint
    (name, version, agents.enabled, llm_mode, mcp.enabled). Paths and service URLs are
    deliberately NOT surfaced (they can leak filesystem layout / env var values) so we
    don't assert on them here — see `project_config.py` for the internal accessors tests.
    """
    assert TEMPLATE_PATH.exists(), f"template missing: {TEMPLATE_PATH}"

    tmp_cfg = tmp_path / "digiproject.yaml"
    shutil.copy(TEMPLATE_PATH, tmp_cfg)

    # Load the template as ground truth for assertions.
    raw = yaml.safe_load(tmp_cfg.read_text()) or {}
    expected_name = raw["project"]["name"]
    expected_version = raw["project"]["version"]
    expected_agents = list(raw["agents"]["enabled"])
    expected_llm_mode = raw["agents"]["llm_mode"]
    expected_mcp_enabled = bool(raw["mcp"]["enabled"])

    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(tmp_cfg))
    # Bust any mtime cache entry a previous test may have populated for this path.
    from digigraph import project_config as pc

    pc._config_cache.clear()

    client = TestClient(app, headers=auth_headers())
    r = client.get("/v1/status")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["service"] == "digigraph"
    assert body["project_name"] == expected_name
    assert body["project_version"] == expected_version
    assert body["agents_enabled"] == expected_agents
    assert body["llm_mode"] == expected_llm_mode
    assert body["mcp_enabled"] is expected_mcp_enabled
    # workflow_profile defaults to "full_stack" when unset in the template
    assert body["workflow_profile"] == "full_stack"

    # Secret hygiene: status must never leak filesystem paths or env values.
    leaky_keys = {"run_data_dir", "indexes_dir", "services", "digisearch_url", "litellm_url"}
    assert not (set(body.keys()) & leaky_keys), f"leaky keys exposed: {body.keys()}"
    # The tmp path string itself must not appear anywhere in the serialized response.
    assert str(tmp_path) not in r.text


@pytest.mark.e2e
def test_status_uses_loader_resolution_for_digiproject_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When DIGI_PROJECT_CONFIG points at a custom file, /v1/status reflects its contents."""
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(
        "project:\n"
        "  name: e2e-status-test\n"
        "  version: '9.9.9'\n"
        "agents:\n"
        "  enabled: [research]\n"
        "  llm_mode: best\n"
        "mcp:\n"
        "  enabled: true\n"
    )
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(cfg))

    from digigraph import project_config as pc

    pc._config_cache.clear()

    client = TestClient(app, headers=auth_headers())
    body = client.get("/v1/status").json()
    assert body["project_name"] == "e2e-status-test"
    assert body["project_version"] == "9.9.9"
    assert body["llm_mode"] == "best"
    assert body["agents_enabled"] == ["research"]
    assert body["mcp_enabled"] is True


@pytest.mark.e2e
def test_status_endpoint_sees_mtime_cache_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end check on the mtime-cache contract: mutating the file between two
    requests must yield the updated values on the second call, without a process restart.
    """
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(
        "project:\n  name: before\n  version: '0.1.0'\nagents:\n  llm_mode: test\n"
    )
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(cfg))

    from digigraph import project_config as pc

    pc._config_cache.clear()

    client = TestClient(app, headers=auth_headers())
    first = client.get("/v1/status").json()
    assert first["project_name"] == "before"
    assert first["llm_mode"] == "test"

    cfg.write_text(
        "project:\n  name: after\n  version: '0.2.0'\nagents:\n  llm_mode: medium\n"
    )
    # Bump mtime deterministically past filesystem granularity.
    import os
    import time

    future = time.time() + 5
    os.utime(cfg, (future, future))

    second = client.get("/v1/status").json()
    assert second["project_name"] == "after"
    assert second["llm_mode"] == "medium"


@pytest.mark.unit
def test_load_project_config_refreshes_on_mtime_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unit-level mtime-cache contract: two DigiProjectConfig.load() calls around a
    file mutation must return the fresh data (spec: re-read on every request, keyed by mtime).
    """
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text("project:\n  name: v1\nagents:\n  llm_mode: test\n")
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(cfg))

    from digigraph import project_config as pc

    pc._config_cache.clear()

    first = DigiProjectConfig.load()
    assert first.project.get("name") == "v1"
    assert first.get_llm_mode() == "test"

    cfg.write_text("project:\n  name: v2\nagents:\n  llm_mode: best\n")
    import os
    import time

    future = time.time() + 5
    os.utime(cfg, (future, future))

    second = DigiProjectConfig.load()
    assert second.project.get("name") == "v2"
    assert second.get_llm_mode() == "best"
