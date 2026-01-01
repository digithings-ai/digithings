"""Unconfigured digisearch must fail loud, not degrade to empty rows.

Root cause: ``DigiProjectConfig.get_digisearch_url()`` fell back to the
docker-only hostname ``http://digisearch:8002`` when neither project config
nor ``DIGISEARCH_URL`` provided it. On a bare runner that hostname never
resolves, hub POSTs transport-fail, the ``digisearch_hub`` breaker opens, and
web grounding returns ``{}`` -> ``RuntimeError('... no rows')``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from digigraph.project_config import DigiProjectConfig

pytestmark = pytest.mark.unit


def test_get_digisearch_url_defaults_empty_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIGISEARCH_URL", raising=False)
    assert DigiProjectConfig({}).get_digisearch_url() == ""


def test_get_digisearch_url_env_flows_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://env-host:8002")
    assert DigiProjectConfig({}).get_digisearch_url() == "http://env-host:8002"


def test_get_digisearch_url_explicit_config_wins_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://env-host:8002")
    cfg = DigiProjectConfig({"services": {"digisearch_url": "http://cfg-host:8002"}})
    assert cfg.get_digisearch_url() == "http://cfg-host:8002"


def test_digisearch_service_base_raises_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digigraph.orchestration import tool_common

    monkeypatch.delenv("DIGISEARCH_URL", raising=False)
    with patch.object(tool_common.DigiProjectConfig, "load", return_value=DigiProjectConfig({})):
        with pytest.raises(RuntimeError, match="digisearch service URL is not configured"):
            tool_common._digisearch_service_base()


def test_digisearch_service_base_error_names_both_config_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digigraph.orchestration import tool_common

    monkeypatch.delenv("DIGISEARCH_URL", raising=False)
    with patch.object(tool_common.DigiProjectConfig, "load", return_value=DigiProjectConfig({})):
        with pytest.raises(RuntimeError) as excinfo:
            tool_common._digisearch_service_base()
    msg = str(excinfo.value)
    assert "services.digisearch_url" in msg
    assert "DIGISEARCH_URL" in msg


def test_digisearch_schema_falls_back_to_static_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catalog builds must not 500 on supported unconfigured deployments
    (e.g. Profile A chat-only): schema degrades to the static fallback, and
    the choke still fails loud at invoke time."""
    from digigraph.orchestration import tool_common
    from digigraph.orchestration.digisearch_tools import _schema_from_digisearch_manifest
    from digigraph.orchestration.registry import ToolContext

    monkeypatch.delenv("DIGISEARCH_URL", raising=False)
    ctx = ToolContext(
        session_id="sess-1",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
        request_id="rid-1",
    )
    with patch.object(tool_common.DigiProjectConfig, "load", return_value=DigiProjectConfig({})):
        schema = _schema_from_digisearch_manifest(ctx, "digisearch")
    assert schema["function"]["name"] == "digisearch"


def test_digisearch_service_base_flows_through_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digigraph.orchestration import tool_common

    monkeypatch.delenv("DIGISEARCH_URL", raising=False)
    cfg = DigiProjectConfig({"services": {"digisearch_url": "http://cfg-host:8002"}})
    with patch.object(tool_common.DigiProjectConfig, "load", return_value=cfg):
        assert tool_common._digisearch_service_base() == "http://cfg-host:8002"

    monkeypatch.setenv("DIGISEARCH_URL", "http://env-host:8002")
    with patch.object(
        tool_common.DigiProjectConfig,
        "load",
        return_value=DigiProjectConfig({}),
    ):
        assert tool_common._digisearch_service_base() == "http://env-host:8002"
