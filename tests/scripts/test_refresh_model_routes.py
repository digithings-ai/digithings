"""Unit tests for scripts/refresh_model_routes.py provider snapshots."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "refresh_model_routes.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("refresh_model_routes", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["refresh_model_routes"] = module
    spec.loader.exec_module(module)
    return module


def test_only_configured_providers_are_queried(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    providers = mod.configured_providers()
    assert "openrouter" in providers
    assert "groq" not in providers


def test_write_snapshot_creates_json(tmp_path: Path) -> None:
    mod = _load()
    snapshot = {"providers": ["openrouter"], "routes": [], "cheapest": None}
    out = mod.write_snapshot(snapshot, tmp_path / "model_routes.json")
    assert out.is_file()


def test_fetch_openrouter_models_requests_priced_list() -> None:
    mod = _load()
    seen: dict[str, object] = {}

    class _Response:
        status_code = 200

        def json(self) -> dict[str, list[object]]:
            return {"data": []}

    class _Client:
        def get(
            self,
            url: str,
            headers: dict[str, str] | None = None,
            params: dict[str, str] | None = None,
            timeout: float | None = None,
        ) -> _Response:
            seen.update(url=url, headers=headers, params=params, timeout=timeout)
            return _Response()

    assert mod.fetch_openrouter_models(_Client(), api_key="test-key") == {"data": []}
    assert seen["url"] == "https://openrouter.ai/api/v1/models"


def test_main_writes_snapshot_for_configured_openrouter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    class _Response:
        status_code = 200

        def json(self) -> dict[str, list[dict[str, object]]]:
            return {
                "data": [
                    {
                        "id": "cheap/tool-model",
                        "context_length": 1000000,
                        "pricing": {"prompt": 0.00000027, "completion": 0.0000011},
                        "supported_parameters": ["tools", "structured_outputs"],
                    }
                ]
            }

    class _Client:
        def get(self, *args: object, **kwargs: object) -> _Response:
            return _Response()

    out = tmp_path / "model_routes.json"
    assert mod.main(["--out", str(out)], client=_Client()) == 0
    assert out.is_file()


def _catalog_payload() -> dict[str, object]:
    return {
        "providers": {
            "openrouter": {
                "models": {
                    "cheap/tool-model": {
                        "tool_call": True,
                        "structured_output": True,
                        "limit": {"context": 1000000},
                        "cost": {"input": 0.27, "output": 1.1},
                    },
                    "expensive/tool-model": {
                        "tool_call": True,
                        "structured_output": True,
                        "limit": {"context": 200000},
                        "cost": {"input": 10.0, "output": 30.0},
                    },
                }
            },
            "fireworks-ai": {
                "models": {
                    "accounts/fireworks/models/cheap-fw": {
                        "tool_call": True,
                        "structured_output": False,
                        "limit": {"context": 128000},
                        "cost": {"input": 0.2, "output": 0.2},
                    }
                }
            },
        }
    }


def test_models_dev_catalog_normalization_converts_pricing() -> None:
    mod = _load()
    routes = mod.normalize_models_dev_catalog(_catalog_payload(), ["openrouter", "fireworks"])
    by_model = {r.model: r for r in routes}
    cheap = by_model["cheap/tool-model"]
    assert cheap.provider == "openrouter"
    assert cheap.prompt_price == pytest.approx(0.27 / 1_000_000)
    assert cheap.context_length == 1000000
    assert cheap.supports_tools is True
    assert cheap.supports_structured_output is True
    assert by_model["accounts/fireworks/models/cheap-fw"].provider == "fireworks"


def test_fetch_models_dev_catalog_uses_public_url() -> None:
    mod = _load()
    seen: dict[str, object] = {}

    class _Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"providers": {}}

    class _Client:
        def get(self, url: str, **kwargs: object) -> _Response:
            seen.update(url=url, headers=kwargs.get("headers"))
            return _Response()

    assert mod.fetch_models_dev_catalog(_Client()) == {"providers": {}}
    assert seen["url"] == "https://models.dev/catalog.json"
    assert seen["headers"] == {}


def test_build_inventory_snapshot_lists_every_route_and_live_ids() -> None:
    mod = _load()
    routes = mod.normalize_models_dev_catalog(_catalog_payload(), ["openrouter"])
    snapshot = mod.build_inventory_snapshot(
        routes,
        live={"openrouter": ["cheap/tool-model"]},
        providers=["openrouter"],
        min_context=64000,
    )
    assert [r["model"] for r in snapshot["routes"]] == [
        "cheap/tool-model",
        "expensive/tool-model",
    ]
    assert snapshot["live"] == {"openrouter": ["cheap/tool-model"]}
    assert "cheapest" not in snapshot


def test_render_table_shows_pricing_and_capabilities() -> None:
    mod = _load()
    routes = mod.normalize_models_dev_catalog(_catalog_payload(), ["openrouter", "fireworks"])
    table = mod.render_table(routes, live={"openrouter": ["cheap/tool-model"]})
    assert "cheap/tool-model" in table
    assert "0.27" in table  # $/1M input, human units
    assert "tools" in table.lower()
    assert "openrouter" in table
    assert "fireworks" in table


def test_render_table_marks_fireworks_live_by_trailing_segment() -> None:
    mod = _load()
    routes = mod.normalize_models_dev_catalog(_catalog_payload(), ["fireworks"])
    table = mod.render_table(routes, live={"fireworks": ["cheap-fw"]})
    assert "accounts/fireworks/models/cheap-fw | " in table
    row = [line for line in table.splitlines() if "cheap-fw" in line][0]
    assert row.split(" | ")[-1] == "yes"  # live column matches by trailing segment
    mod = _load()
    routes = mod.normalize_models_dev_catalog(_catalog_payload(), ["openrouter", "fireworks"])
    table = mod.render_table(routes, live={"openrouter": ["cheap/tool-model"]})
    assert "cheap/tool-model" in table
    assert "0.27" in table  # $/1M input, human units
    assert "tools" in table.lower()
    assert "openrouter" in table
    assert "fireworks" in table


def test_main_writes_full_inventory_and_prints_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    class _Response:
        status_code = 200

        def __init__(self, payload: object) -> None:
            self._payload = payload

        def json(self) -> object:
            return self._payload

    class _Client:
        def get(self, url: str, **kwargs: object) -> _Response:
            if "models.dev" in url:
                return _Response(_catalog_payload())
            return _Response({"data": [{"id": "cheap/tool-model"}]})

    out = tmp_path / "model_routes.json"
    assert mod.main(["--out", str(out)], client=_Client()) == 0
    snapshot = __import__("json").loads(out.read_text(encoding="utf-8"))
    assert [r["model"] for r in snapshot["routes"]] == [
        "cheap/tool-model",
        "expensive/tool-model",
    ]
    assert snapshot["live"]["openrouter"] == ["cheap/tool-model"]
    assert "cheapest" not in snapshot
    assert "cheap/tool-model" in capsys.readouterr().out


def test_fetch_openai_models_uses_models_path() -> None:
    mod = _load()
    seen: dict[str, object] = {}

    class _Response:
        status_code = 200

        def json(self) -> dict[str, list[object]]:
            return {"data": []}

    class _Client:
        def get(self, url: str, **kwargs: object) -> _Response:
            seen["url"] = url
            return _Response()

    assert mod.fetch_openai_models(_Client(), base_url="https://api.groq.com/openai/v1") == {
        "data": []
    }
    assert seen["url"] == "https://api.groq.com/openai/v1/models"


def test_fetch_ollama_tags_uses_tags_path() -> None:
    mod = _load()
    seen: dict[str, object] = {}

    class _Response:
        status_code = 200

        def json(self) -> dict[str, list[object]]:
            return {"models": []}

    class _Client:
        def get(self, url: str, **kwargs: object) -> _Response:
            seen["url"] = url
            return _Response()

    assert mod.fetch_ollama_tags(_Client(), base_url="http://localhost:11434") == {"models": []}
    assert seen["url"] == "http://localhost:11434/api/tags"


def test_fetch_fireworks_models_uses_account_path() -> None:
    mod = _load()
    seen: dict[str, object] = {}

    class _Response:
        status_code = 200

        def json(self) -> dict[str, list[object]]:
            return {"models": []}

    class _Client:
        def get(self, url: str, **kwargs: object) -> _Response:
            seen["url"] = url
            return _Response()

    payload = mod.fetch_fireworks_models(_Client(), account_id="acct", api_key="k")
    assert payload == {"models": []}
    assert seen["url"] == "https://api.fireworks.ai/v1/accounts/acct/models"
