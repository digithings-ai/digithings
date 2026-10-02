"""Unit tests for scripts/refresh_model_catalog.py (#4994).

models.dev is the catalog this repo normalizes into ``config/model-catalog.json``
and the generated digichat TypeScript module. Two properties are load-bearing and
both are pinned here.

First, *unknown is never false*. models.dev omits ``cost`` on 8 of xai's 13 rows
and 10 of groq's 16, omits ``structured_output`` on 18 of openai's 53, and ships
``limit.context == 0`` for image models like ``chatgpt-image-latest``. Reading any
of those absences as a falsy value would silently mis-bucket real models -- a
missing price read as ``0`` would classify a third of two providers' catalogs as
free, and a missing capability read as ``False`` would hide tool-using models from
any capability filter. Every degradation rule therefore normalizes to ``null`` or
to a tier of ``None`` (which lands in the unfiltered ``all`` bucket), never to a
default.

Second, ``--check`` must never touch the network, or the CI drift guard would
fail on models.dev's availability instead of on repo drift. That is pinned by
monkeypatching ``fetch_catalog`` to raise.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "refresh_model_catalog.py"

#: The exact key set the spec's data model defines for a normalized entry. A new
#: key in the generator must be a deliberate schema change (SCHEMA_VERSION bump),
#: so this is an equality assertion rather than a subset check.
ENTRY_KEYS = {
    "id",
    "label",
    "cost_input_usd_per_million",
    "cost_output_usd_per_million",
    "context_window",
    "max_output_tokens",
    "modalities_input",
    "modalities_output",
    "tool_call",
    "structured_output",
    "reasoning",
    "vision",
    "attachment",
    "open_weights",
    "tier",
}


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("refresh_model_catalog", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["refresh_model_catalog"] = module
    spec.loader.exec_module(module)
    return module


def _models_dev_payload() -> dict[str, Any]:
    """Minimal models.dev ``catalog.json`` body: providers -> {models: {id: {...}}}."""
    return {
        "providers": {
            "openai": {
                "id": "openai",
                "models": {
                    "gpt-5.4": {
                        "id": "gpt-5.4",
                        "name": "GPT-5.4",
                        "cost": {"input": 2.5, "output": 15},
                        "limit": {"context": 1050000, "output": 128000},
                        "modalities": {"input": ["text", "image"], "output": ["text"]},
                        "tool_call": True,
                        "reasoning": True,
                        "attachment": True,
                        "open_weights": False,
                    },
                    # Above the $3/1M floor, so the end-to-end tier derivation is
                    # exercised and not only derive_tier() in isolation.
                    "gpt-6-luna": {
                        "id": "gpt-6-luna",
                        "name": "GPT-6 Luna",
                        "cost": {"input": 12, "output": 40},
                        "limit": {"context": 400000, "output": 64000},
                        "tool_call": True,
                        "structured_output": True,
                        "open_weights": False,
                    },
                },
            }
        }
    }


def test_normalize_keeps_a_fully_populated_model() -> None:
    mod = _load()
    out = mod.normalize_catalog(_models_dev_payload())
    entry = out["models"]["openai"][0]
    assert entry["id"] == "gpt-5.4"
    assert entry["label"] == "GPT-5.4"
    assert entry["cost_input_usd_per_million"] == 2.5
    assert entry["cost_output_usd_per_million"] == 15.0
    assert entry["context_window"] == 1050000
    assert entry["max_output_tokens"] == 128000
    assert entry["vision"] is True
    assert entry["modalities_input"] == ["text", "image"]
    assert entry["modalities_output"] == ["text"]
    assert entry["tool_call"] is True
    assert entry["reasoning"] is True
    assert entry["attachment"] is True
    assert entry["open_weights"] is False
    assert entry["structured_output"] is None  # upstream said nothing
    # $2.50/1M is under the $3 floor, and gpt-5.4 is not open-weight, so it gets
    # no tier at all -- the real upstream entry behaves this way. An unpriced or
    # sub-floor model landing in `all` only is the intended outcome, not a gap.
    assert entry["tier"] is None


def test_normalize_derives_a_tier_above_the_price_floor() -> None:
    mod = _load()
    out = mod.normalize_catalog(_models_dev_payload())
    flagship = next(e for e in out["models"]["openai"] if e["id"] == "gpt-6-luna")
    assert flagship["tier"] == "flagship"
    assert flagship["structured_output"] is True
    assert flagship["label"] == "GPT-6 Luna"  # falls back to id when name is absent


def test_a_model_with_no_modalities_is_text_only_not_vision() -> None:
    mod = _load()
    out = mod.normalize_catalog(_models_dev_payload())
    flagship = next(e for e in out["models"]["openai"] if e["id"] == "gpt-6-luna")
    assert flagship["modalities_input"] == []
    assert flagship["vision"] is False


def test_meta_records_the_generator_constant_verbatim() -> None:
    mod = _load()
    meta = mod.normalize_catalog(_models_dev_payload())["_meta"]
    assert meta["schema_version"] == mod.SCHEMA_VERSION
    assert meta["source"] == "models.dev"
    assert meta["source_url"] == mod.MODELS_DEV_CATALOG_URL
    assert meta["providers"] == list(mod.CATALOG_PROVIDERS)
    assert meta["providers"] == sorted(mod.CATALOG_PROVIDERS)
    assert isinstance(meta["fetched_at"], str) and meta["fetched_at"]


def test_catalog_providers_constant_is_sorted_and_matches_the_spec() -> None:
    mod = _load()
    assert list(mod.CATALOG_PROVIDERS) == sorted(mod.CATALOG_PROVIDERS)
    assert list(mod.CATALOG_PROVIDERS) == [
        "anthropic",
        "deepseek",
        "fireworks-ai",
        "google",
        "groq",
        "ollama-cloud",
        "openai",
        "openrouter",
        "togetherai",
        "xai",
    ]


def test_absent_cost_normalizes_to_null_not_zero() -> None:
    mod = _load()
    payload = _models_dev_payload()
    del payload["providers"]["openai"]["models"]["gpt-5.4"]["cost"]
    entry = mod.normalize_catalog(payload)["models"]["openai"][0]
    assert entry["cost_input_usd_per_million"] is None
    assert entry["cost_output_usd_per_million"] is None
    assert entry["tier"] is None  # never "free", never "flagship"


def test_partial_cost_block_leaves_the_missing_side_null() -> None:
    mod = _load()
    payload = _models_dev_payload()
    payload["providers"]["openai"]["models"]["gpt-5.4"]["cost"] = {"output": 15}
    entry = mod.normalize_catalog(payload)["models"]["openai"][0]
    assert entry["cost_input_usd_per_million"] is None
    assert entry["cost_output_usd_per_million"] == 15.0
    assert entry["tier"] is None


def test_zero_context_window_normalizes_to_null() -> None:
    mod = _load()
    payload = _models_dev_payload()
    payload["providers"]["openai"]["models"]["gpt-5.4"]["limit"]["context"] = 0
    entry = mod.normalize_catalog(payload)["models"]["openai"][0]
    assert entry["context_window"] is None


def test_absent_structured_output_is_null_not_false() -> None:
    # 8 of openai's 53 rows omit it. Reading absence as False would hide
    # tool-using models from any capability filter.
    mod = _load()
    entry = mod.normalize_catalog(_models_dev_payload())["models"]["openai"][0]
    assert entry["structured_output"] is None


def test_free_requires_both_costs_present_and_zero() -> None:
    mod = _load()
    assert mod.derive_tier(0.0, 0.0, False) == "free"
    assert mod.derive_tier(0.0, None, False) is None
    assert mod.derive_tier(None, 0.0, False) is None
    assert mod.derive_tier(None, None, False) is None


def test_flagship_uses_the_carried_over_price_floor() -> None:
    mod = _load()
    assert mod.FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M == 3.0
    assert mod.derive_tier(mod.FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M, 5.0, False) == "flagship"
    assert mod.derive_tier(mod.FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M - 0.01, 5.0, False) is None


def test_tier_order_is_free_then_flagship_then_opensource() -> None:
    mod = _load()
    assert mod.TIER_ORDER == ("free", "flagship", "opensource")
    assert mod.derive_tier(0.0, 0.0, True) == "free"
    assert mod.derive_tier(9.0, 9.0, True) == "flagship"
    assert mod.derive_tier(0.5, 0.5, True) == "opensource"
    assert mod.derive_tier(0.5, 0.5, False) is None


def test_provider_upstream_but_not_declared_is_skipped() -> None:
    # models.dev carries 226 providers; shipping all of them would make the
    # vendored file 5.7 MB for models this repo cannot route.
    mod = _load()
    payload = _models_dev_payload()
    payload["providers"]["ollama"] = {
        "id": "ollama",
        "models": {"llama3.2": {"id": "llama3.2", "name": "Llama 3.2"}},
    }
    out = mod.normalize_catalog(payload)
    assert "ollama" not in out["models"]
    assert out["_meta"]["providers"] == list(mod.CATALOG_PROVIDERS)


def test_entries_are_sorted_by_id_within_each_provider() -> None:
    mod = _load()
    payload = _models_dev_payload()
    models = payload["providers"]["openai"]["models"]
    for model_id in ("gpt-5.4", "a-model", "z-model"):
        models[model_id] = {"id": model_id, "name": model_id.upper()}
    ids = [entry["id"] for entry in mod.normalize_catalog(payload)["models"]["openai"]]
    assert ids == sorted(ids)
    assert ids == ["a-model", "gpt-5.4", "gpt-6-luna", "z-model"]


def test_endpoint_and_credential_fields_never_survive_normalization() -> None:
    # The catalog is a module import on the digichat side. A base URL, env var
    # name, or npm package in it would turn a metadata file into a routing
    # surface that has to be SSRF-audited, and would put credential *names* in a
    # file the browser bundle imports.
    mod = _load()
    payload = _models_dev_payload()
    payload["providers"]["openai"].update(
        {
            "api": "https://api.openai.com/v1",
            "env": ["OPENAI_API_KEY"],
            "npm": "@ai-sdk/openai",
            "doc": "https://platform.openai.com/docs",
        }
    )
    payload["providers"]["openai"]["models"]["gpt-5.4"]["url"] = "https://example.invalid"
    out = mod.normalize_catalog(payload)
    blob = json.dumps(out)
    for forbidden in ("api.openai.com", "OPENAI_API_KEY", "@ai-sdk/openai", "example.invalid"):
        assert forbidden not in blob


def test_emitted_entry_keys_are_exactly_the_schema() -> None:
    mod = _load()
    out = mod.normalize_catalog(_models_dev_payload())
    for provider_entries in out["models"].values():
        for entry in provider_entries:
            assert set(entry) == ENTRY_KEYS


def test_a_declared_provider_upstream_never_had_still_normalizes_to_empty_list() -> None:
    # models.dev drops and re-adds providers as vendors change. A missing provider
    # must produce an empty list, not a KeyError that aborts a refresh at 3am.
    mod = _load()
    out = mod.normalize_catalog(_models_dev_payload())
    assert out["models"]["anthropic"] == []
    assert out["models"]["groq"] == []


def test_a_provider_whose_models_block_is_not_a_dict_normalizes_to_empty_list() -> None:
    mod = _load()
    payload = _models_dev_payload()
    payload["providers"]["openai"]["models"] = []
    assert mod.normalize_catalog(payload)["models"]["openai"] == []


# --------------------------------------------------------------------------
# Task 2 — the fetcher, the TypeScript renderer, and the writer
# --------------------------------------------------------------------------


def _catalog(mod: Any) -> dict[str, Any]:
    return mod.normalize_catalog(_models_dev_payload(), fetched_at="2026-10-03T00:00:00+00:00")


def test_write_artifacts_refuses_to_write_an_empty_catalog(tmp_path: Path) -> None:
    # An upstream hiccup that yields `providers: {}` must not overwrite a good
    # catalog with 606 rows of nothing -- that would delete every model's
    # metadata in one command and read as a legitimate deletion in the diff.
    mod = _load()
    empty = mod.normalize_catalog({}, fetched_at="2026-10-03T00:00:00+00:00")
    with pytest.raises(mod.CatalogRefreshError):
        mod.write_artifacts(empty, json_path=tmp_path / "c.json", ts_path=tmp_path / "c.ts")
    assert not (tmp_path / "c.json").exists()
    assert not (tmp_path / "c.ts").exists()


def test_write_artifacts_round_trips_the_json(tmp_path: Path) -> None:
    mod = _load()
    catalog = _catalog(mod)
    json_path = tmp_path / "model-catalog.json"
    ts_path = tmp_path / "model-catalog.generated.ts"
    mod.write_artifacts(catalog, json_path=json_path, ts_path=ts_path)
    assert json.loads(json_path.read_text(encoding="utf-8")) == catalog
    assert ts_path.is_file()


def test_rendered_typescript_is_byte_stable_across_runs() -> None:
    # `make model-catalog-check` compares this rendering byte-for-byte, so any
    # run-to-run wobble (dict ordering, a timestamp, a set) would fail CI on a
    # tree nobody touched.
    mod = _load()
    catalog = _catalog(mod)
    assert mod.render_typescript_module(catalog) == mod.render_typescript_module(catalog)


def test_rendered_typescript_carries_the_catalog_and_no_other_timestamp() -> None:
    mod = _load()
    rendered = mod.render_typescript_module(_catalog(mod))
    assert 'from "./model-catalog"' in rendered
    assert "MODEL_CATALOG_BY_PROVIDER" in rendered
    assert "gpt-6-luna" in rendered
    # The one provenance value allowed to appear; nothing else may be a clock read.
    assert "2026-10-03T00:00:00+00:00" in rendered
    assert "generated at" not in rendered.lower()


def _literal_after(text: str, marker: str) -> Any:
    """The single JSON value that follows ``marker``, parsed."""
    assert marker in text, f"{marker!r} missing from the rendered module"
    _, _, rest = text.partition(marker)
    value, _ = json.JSONDecoder().raw_decode(rest.lstrip())
    return value


def test_rendered_typescript_is_valid_json_per_export() -> None:
    # The module is data, not code paths, so each export must be a plain JSON
    # literal. A hand-rolled bracket would be unparseable and would ship a
    # module that only builds if someone happened to fix it.
    mod = _load()
    rendered = mod.render_typescript_module(_catalog(mod))
    assert _literal_after(rendered, "MODEL_CATALOG_SCHEMA_VERSION = ") == mod.SCHEMA_VERSION
    assert _literal_after(rendered, "MODEL_CATALOG_PROVIDERS = ") == list(mod.CATALOG_PROVIDERS)
    meta = _literal_after(rendered, "MODEL_CATALOG_META = ")
    assert meta["fetched_at"] == "2026-10-03T00:00:00+00:00"
    by_provider = _literal_after(
        rendered, "MODEL_CATALOG_BY_PROVIDER: Record<string, readonly ModelCatalogEntry[]> = "
    )
    assert list(by_provider) == list(mod.CATALOG_PROVIDERS)
    assert [e["id"] for e in by_provider["openai"]] == ["gpt-5.4", "gpt-6-luna"]


def test_fetch_catalog_uses_an_explicit_timeout_and_raises_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load()
    seen: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"providers": {}}

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            seen["init"] = kwargs

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def get(self, url: str, **kwargs: Any) -> _Response:
            seen["url"] = url
            seen["get"] = kwargs
            return _Response()

    monkeypatch.setattr(mod.httpx, "Client", _Client)
    assert mod.fetch_catalog(timeout=12.5) == {"providers": {}}
    # A hung CDN must not become a hung refresh; an unbounded default is how a
    # 5.7 MB pull turns into an indefinite job with no operator signal.
    assert seen["init"] == {"timeout": 12.5}
    assert seen["url"] == mod.MODELS_DEV_CATALOG_URL
    assert seen["get"] == {"timeout": 12.5}


def test_fetch_catalog_wraps_transport_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def get(self, url: str, **kwargs: Any) -> None:
            raise mod.httpx.TimeoutException("read timed out")

    monkeypatch.setattr(mod.httpx, "Client", _Client)
    with pytest.raises(mod.CatalogRefreshError):
        mod.fetch_catalog()


def test_main_offline_rewrites_only_the_typescript_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    json_path = tmp_path / "model-catalog.json"
    ts_path = tmp_path / "model-catalog.generated.ts"
    catalog = _catalog(mod)
    json_path.write_text(json.dumps(catalog), encoding="utf-8")

    monkeypatch.setattr(
        mod, "CATALOG_JSON_PATH", json_path, raising=False
    )
    monkeypatch.setattr(mod, "TS_MODULE_PATH", ts_path, raising=False)
    monkeypatch.setattr(
        mod,
        "fetch_catalog",
        lambda *a, **k: pytest.fail("--offline must not fetch"),
    )
    assert mod.main(["--offline"]) == 0
    assert ts_path.is_file()
    # The committed JSON is the source of truth offline; re-writing it would
    # churn the file it was rendered from.
    assert json.loads(json_path.read_text(encoding="utf-8")) == catalog


def test_main_writes_both_artifacts_after_fetching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    json_path = tmp_path / "model-catalog.json"
    ts_path = tmp_path / "model-catalog.generated.ts"
    monkeypatch.setattr(mod, "CATALOG_JSON_PATH", json_path, raising=False)
    monkeypatch.setattr(mod, "TS_MODULE_PATH", ts_path, raising=False)
    monkeypatch.setattr(mod, "fetch_catalog", lambda *a, **k: _models_dev_payload())

    assert mod.main([]) == 0
    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["_meta"]["source"] == mod.CATALOG_SOURCE
    assert [e["id"] for e in written["models"]["openai"]] == ["gpt-5.4", "gpt-6-luna"]
    assert "gpt-6-luna" in ts_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Task 3 — the network-free drift guard
# --------------------------------------------------------------------------

_EXEMPTION_FILE = {
    "exemptions": [
        {
            "id": "ollama/deepseek-r1:14b",
            "source": "config/model_modes.local.yaml",
            "reason": "local ollama is per-machine, not a catalogued provider",
        }
    ]
}


def _write_exemptions(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "exemptions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_assert_invariants_accepts_a_clean_catalog(tmp_path: Path) -> None:
    mod = _load()
    clean = _write_exemptions(tmp_path, _EXEMPTION_FILE)
    assert mod.assert_invariants(_catalog(mod), exemptions_path=clean) == []


@pytest.mark.parametrize(
    ("mutate", "expected_fragment"),
    [
        pytest.param(
            lambda c: c["_meta"].__setitem__("schema_version", 99),
            "schema_version",
            id="schema-version-drifted",
        ),
        pytest.param(
            lambda c: c["_meta"].__setitem__("providers", list(reversed(c["_meta"]["providers"]))),
            "sorted",
            id="providers-unsorted",
        ),
        pytest.param(
            lambda c: c["_meta"]["providers"].remove("groq"),
            "providers",
            id="providers-missing-a-declared-one",
        ),
        pytest.param(
            lambda c: c["models"].__setitem__("bedrock", []),
            "models",
            id="model-key-not-in-meta",
        ),
        pytest.param(
            lambda c: c["models"]["openai"].append(dict(c["models"]["openai"][0])),
            "duplicate",
            id="duplicate-id-within-a-provider",
        ),
        pytest.param(
            lambda c: c["models"]["openai"][0].__setitem__("context_window", 0),
            "context_window",
            id="context-window-not-positive",
        ),
        pytest.param(
            lambda c: c["models"]["openai"][0].__setitem__("cost_input_usd_per_million", -1),
            "cost",
            id="negative-cost",
        ),
        pytest.param(
            lambda c: c["models"]["openai"][0].__setitem__("structured_output", "yes"),
            "structured_output",
            id="structured-output-not-tri-state",
        ),
        pytest.param(
            lambda c: c["models"]["openai"][0].__setitem__("tier", "premium"),
            "tier",
            id="unknown-tier",
        ),
        pytest.param(
            lambda c: c["models"]["openai"].reverse(),
            "sorted",
            id="entries-unsorted",
        ),
        pytest.param(
            lambda c: c["models"]["openai"][0].__setitem__("api", "https://api.example.com"),
            "api",
            id="routing-key-leaked",
        ),
    ],
)
def test_assert_invariants_catches_each_violation(
    tmp_path: Path, mutate: Any, expected_fragment: str
) -> None:
    mod = _load()
    catalog = _catalog(mod)
    mutate(catalog)
    violations = mod.assert_invariants(
        catalog, exemptions_path=_write_exemptions(tmp_path, _EXEMPTION_FILE)
    )
    assert any(expected_fragment in v for v in violations), violations


def test_assert_invariants_flags_an_exemption_without_a_reason(tmp_path: Path) -> None:
    mod = _load()
    exemptions = _write_exemptions(
        tmp_path, {"exemptions": [{"id": "ollama/x", "source": "config/y.yaml", "reason": "  "}]}
    )
    violations = mod.assert_invariants(_catalog(mod), exemptions_path=exemptions)
    assert any("reason" in v for v in violations), violations


def test_assert_invariants_flags_an_exemption_that_is_no_longer_needed(tmp_path: Path) -> None:
    # An exemption that models.dev has caught up with is a stale escape hatch:
    # leaving it costs nothing today and silently excuses a future real problem
    # with that same id.
    mod = _load()
    exemptions = _write_exemptions(
        tmp_path,
        {"exemptions": [{"id": "gpt-5.4", "source": "config/y.yaml", "reason": "stale"}]},
    )
    violations = mod.assert_invariants(_catalog(mod), exemptions_path=exemptions)
    assert any("no longer needed" in v for v in violations), violations


def test_check_passes_on_a_consistent_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    catalog = _catalog(mod)
    json_path = tmp_path / "model-catalog.json"
    ts_path = tmp_path / "model-catalog.generated.ts"
    json_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    ts_path.write_text(mod.render_typescript_module(catalog), encoding="utf-8")
    _wire_paths(mod, monkeypatch, json_path, ts_path, _write_exemptions(tmp_path, _EXEMPTION_FILE))
    monkeypatch.setattr(mod, "fetch_catalog", lambda *a, **k: pytest.fail("--check must not fetch"))
    assert mod.main(["--check"]) == 0


def test_check_fails_when_the_typescript_module_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The failure mode this guards is the important one: someone edits the JSON
    # by hand, or a generator change lands without a re-render, and the browser
    # bundle silently serves yesterday's catalog.
    mod = _load()
    catalog = _catalog(mod)
    json_path = tmp_path / "model-catalog.json"
    ts_path = tmp_path / "model-catalog.generated.ts"
    json_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    ts_path.write_text(mod.render_typescript_module(catalog).replace("gpt-6-luna", "gpt-6-sun"))
    _wire_paths(mod, monkeypatch, json_path, ts_path, _write_exemptions(tmp_path, _EXEMPTION_FILE))
    assert mod.main(["--check"]) == 1
    out = capsys.readouterr().out
    assert "model-catalog.generated.ts" in out
    assert "--offline" in out


def test_check_fails_when_the_committed_json_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    json_path = tmp_path / "model-catalog.json"
    ts_path = tmp_path / "model-catalog.generated.ts"
    _wire_paths(mod, monkeypatch, json_path, ts_path, _write_exemptions(tmp_path, _EXEMPTION_FILE))
    with pytest.raises(mod.CatalogRefreshError):
        mod.main(["--check"])


def test_check_never_fetches_even_when_the_json_is_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # CI must be able to run the drift guard with no egress. A guard that
    # silently reaches for the network is a guard whose result depends on a
    # third party's uptime.
    mod = _load()
    catalog = _catalog(mod)
    json_path = tmp_path / "model-catalog.json"
    ts_path = tmp_path / "model-catalog.generated.ts"
    json_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    ts_path.write_text(mod.render_typescript_module(catalog), encoding="utf-8")
    _wire_paths(mod, monkeypatch, json_path, ts_path, _write_exemptions(tmp_path, _EXEMPTION_FILE))

    def _explode(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("--check called fetch_catalog")

    monkeypatch.setattr(mod, "fetch_catalog", _explode)
    assert mod.check_artifacts() == 0


def _wire_paths(
    mod: Any,
    monkeypatch: pytest.MonkeyPatch,
    json_path: Path,
    ts_path: Path,
    exemptions_path: Path,
) -> None:
    monkeypatch.setattr(mod, "CATALOG_JSON_PATH", json_path)
    monkeypatch.setattr(mod, "TS_MODULE_PATH", ts_path)
    monkeypatch.setattr(mod, "EXEMPTIONS_PATH", exemptions_path)


# --------------------------------------------------------------------------
# Task 4 -- the BYOK provider map and the author-strip (D7)


def test_byok_provider_map_targets_only_vendored_providers() -> None:
    mod = _load()
    targets = set(mod.BYOK_PROVIDER_TO_CATALOG_PROVIDER.values())
    unknown = targets - set(mod.CATALOG_PROVIDERS)
    assert not unknown, f"BYOK map points at providers we do not vendor: {sorted(unknown)}"


def test_byok_provider_map_carries_the_three_documented_renames() -> None:
    # models.dev spells these three differently from config/byok-providers.json.
    mod = _load()
    mapping = mod.BYOK_PROVIDER_TO_CATALOG_PROVIDER
    assert mapping["gemini"] == "google"
    assert mapping["together"] == "togetherai"
    assert mapping["fireworks"] == "fireworks-ai"


def test_byok_provider_lookup_returns_none_for_an_unmapped_id() -> None:
    # None, never a guess: silently coercing an unknown provider to a default is
    # how a model id ends up validated against the wrong provider's list.
    mod = _load()
    assert mod.byok_provider_to_catalog_provider("ollama-local") is None
    assert mod.byok_provider_to_catalog_provider("openai") == "openai"


def test_strip_author_drops_everything_before_the_first_slash() -> None:
    mod = _load()
    assert mod.strip_author("gemini/gemini-2.5-flash") == "gemini-2.5-flash"
    assert mod.strip_author("gpt-4o") == "gpt-4o"
    assert mod.strip_author("") == ""


def test_rendered_typescript_exports_the_byok_provider_map() -> None:
    mod = _load()
    rendered = mod.render_typescript_module(_catalog(mod))
    assert "MODEL_CATALOG_BYOK_PROVIDER_MAP" in rendered
    literal = _literal_after(rendered, "MODEL_CATALOG_BYOK_PROVIDER_MAP: Record<string, string> = ")
    assert literal == dict(mod.BYOK_PROVIDER_TO_CATALOG_PROVIDER)