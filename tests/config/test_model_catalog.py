"""The committed model catalog must still cover every model we pin (#4994).

`config/model-catalog.json` is a generated snapshot of models.dev, refreshed by
`scripts/refresh_model_catalog.py`. Its value is not the data — it is the check:
a model we ship a fallback pin for, a route we bill against, or a provider a
BYOK key is accepted for, must still resolve upstream. When a vendor retires a
model, this file is what notices.

The checks are **scoped by confidence**, because models.dev is a curated
capability database, not a live route registry (spec D8):

* **Strict** — `config/byok-providers.json` ``fallbackModels``. These are the
  only ids the BYOK picker offers with no key, so a miss is a user-visible dead
  option. Anything models.dev legitimately cannot carry is listed in
  `config/model-catalog-exemptions.json` with a reason.
* **Advisory** — the 149 `model_list` routes across `config/litellm*.yaml`.
  models.dev's openrouter slice is 390 rows and does not carry our ``:free``
  slugs consistently, and its ollama-cloud ids carry no ``:cloud`` tag, so
  misses here are a known blind spot. Those warn; they never fail.

Every path is resolved from ``__file__``, not ``cwd`` — pytest is invoked from
several directories across this repo and CI.
"""

from __future__ import annotations

import functools
import importlib.util
import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any  # score:allow untyped any

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "config"
CATALOG_PATH = CONFIG / "model-catalog.json"
EXEMPTIONS_PATH = CONFIG / "model-catalog-exemptions.json"
BYOK_PROVIDERS_PATH = CONFIG / "byok-providers.json"
GENERATOR_PATH = REPO_ROOT / "scripts" / "refresh_model_catalog.py"

#: The four LiteLLM route tables. `litellm.cheaperinference.yaml` is included:
#: it is the upstream every digiquant tier pool is annotated against (#3660).
LITELLM_YAMLS = (
    CONFIG / "litellm.yaml",
    CONFIG / "litellm.cheaperinference.yaml",
    CONFIG / "litellm.dev.yaml",
    CONFIG / "litellm.omniroute.yaml",
)

#: Routing suffixes LiteLLM appends to an OpenRouter slug. They are not part of
#: the model id, so they are stripped before comparing against the catalog.
_ROUTE_SUFFIX = re.compile(r":(free|online|extended)$")


@functools.lru_cache(maxsize=1)
def _load_generator() -> Any:
    """The generator is the single owner of the provider map and the author-strip.

    Imported by path because `scripts/` is not a package, matching
    tests/scripts/test_refresh_model_routes.py. Cached so the per-model lookups
    below do not re-exec the module for every id.
    """
    spec = importlib.util.spec_from_file_location("refresh_model_catalog", GENERATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["refresh_model_catalog"] = module
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> Any:
    assert path.is_file(), f"{path} is missing — run `make model-catalog`"
    return json.loads(path.read_text(encoding="utf-8"))


def load_catalog() -> dict:
    return _read_json(CATALOG_PATH)


def load_byok_providers() -> list[dict]:
    return _read_json(BYOK_PROVIDERS_PATH)


def load_exemptions() -> list[dict]:
    return list(_read_json(EXEMPTIONS_PATH)["exemptions"])


def resolved_ids(catalog: dict) -> set[str]:
    """Every catalog id plus its author-stripped form, for suffix-free lookups."""
    strip_author = _load_generator().strip_author
    return {
        stripped
        for entries in catalog["models"].values()
        for model_id in (entry["id"] for entry in entries)
        for stripped in (model_id, strip_author(model_id))
    }


def litellm_route_models() -> set[str]:
    """Every upstream model id the LiteLLM route tables point at."""
    models: set[str] = set()
    for path in LITELLM_YAMLS:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{path} must parse as a mapping"
        for entry in data["model_list"]:
            params = entry.get("litellm_params") or {}
            if isinstance(params.get("model"), str):
                models.add(params["model"])
    return models


# ── Strict: BYOK fallback pins ────────────────────────────────────────────────


def test_every_byok_fallback_model_exists_in_the_catalog() -> None:
    """The load-bearing check. A retired fallback is a dead option in the picker.

    xai's was `grok-4-3`, which models.dev only carries as `grok-4.3`; the
    anthropic pins were dated `-4` ids whose generation models.dev no longer
    lists at all. All six were **replaced** in #5000, after each successor was
    verified against the provider's own API (or, for the three anthropic ids
    with no key on hand, against two independent public keyspaces: models.dev
    and LiteLLM's pricing table). The replacement was a **routing** change, not
    a catalog edit: every `fallbackModels` entry must also be a `model_name` in
    `config/litellm.yaml`
    (`test_every_advertised_byok_preset_is_a_litellm_model_group`, #3605), so a
    wrong `litellm_params.model` is a 500 on every BYOK chat that picks it.
    `config/model-catalog-exemptions.json` is now empty; see
    `docs/MODEL_CATALOG.md` for what a future retired pin has to satisfy before
    it can be swapped.
    """
    generator = _load_generator()
    exempt_ids = {e["id"] for e in load_exemptions()}
    catalog = load_catalog()

    unresolved: list[str] = []
    for entry in load_byok_providers():
        provider = generator.byok_provider_to_catalog_provider(entry["id"])
        assert provider is not None, f"no catalog provider mapped for BYOK {entry['id']}"
        assert provider in catalog["models"], f"catalog has no slice for {provider}"
        known = {generator.strip_author(m["id"]) for m in catalog["models"][provider]}
        for model in entry.get("fallbackModels", []):
            if model in exempt_ids:
                continue
            if generator.strip_author(model) not in known:
                unresolved.append(f"{entry['id']}: {model} (catalog provider {provider})")
    assert not unresolved, "pinned BYOK models the catalog does not carry:\n" + "\n".join(
        unresolved
    )


def test_every_byok_provider_maps_to_a_vendored_catalog_provider() -> None:
    """A new BYOK provider without a D7 mapping is invisible to the catalog."""
    generator = _load_generator()
    catalog = load_catalog()
    for entry in load_byok_providers():
        provider = generator.byok_provider_to_catalog_provider(entry["id"])
        assert provider in catalog["models"], f"{entry['id']} -> {provider} is not vendored"


# ── Strict: the exemption file ────────────────────────────────────────────────


def test_every_exemption_carries_a_reason() -> None:
    for exemption in load_exemptions():
        reason = str(exemption.get("reason") or "").strip()
        assert reason, f"exemption {exemption.get('id')!r} has no reason"


def test_no_exemption_is_stale() -> None:
    """An exemption the catalog now resolves is a silent hole in the strict check.

    Same rule the generator asserts in `--check`; pinned here too so a drifted
    snapshot fails this suite rather than waiting for the CI drift guard.
    """
    generator = _load_generator()
    known = resolved_ids(load_catalog())
    for exemption in load_exemptions():
        model_id = str(exemption["id"])
        assert generator.strip_author(model_id) not in known, (
            f"{model_id!r} is exempt but the catalog now resolves it — delete the exemption"
        )


# ── Strict: the artifact itself ───────────────────────────────────────────────


def test_committed_catalog_satisfies_every_data_model_invariant() -> None:
    """Delegates to the generator rather than restating the eight invariants here.

    The rules live once, next to the normalizer that can break them; this test
    only asserts they hold for the committed bytes.
    """
    generator = _load_generator()
    violations = generator.assert_invariants(load_catalog(), exemptions_path=EXEMPTIONS_PATH)
    assert not violations, "config/model-catalog.json invariants violated:\n" + "\n".join(
        violations
    )


def test_generated_typescript_module_is_in_sync() -> None:
    """The TS module is generated from the JSON; `--check` compares them byte-for-byte.

    Asserted here as well so the digichat-side tests fail on drift even when the
    CI path filter that runs `--check` is not in play.
    """
    generator = _load_generator()
    expected = generator.render_typescript_module(load_catalog())
    on_disk = REPO_ROOT / "apps" / "digichat" / "src" / "lib" / "model-catalog.generated.ts"
    assert on_disk.is_file(), f"{on_disk} is missing — run `make model-catalog`"
    assert on_disk.read_text(encoding="utf-8") == expected, (
        "model-catalog.generated.ts is stale — run `make model-catalog`"
    )


# ── Advisory: LiteLLM route spellings ─────────────────────────────────────────


def test_litellm_routes_resolve_advisory() -> None:
    """models.dev is a curated DB, not a live route registry.

    Its openrouter slice is 390 rows and does not carry our ``:free`` slugs
    consistently, and its ollama-cloud ids carry no ``:cloud`` tag. Roughly 38 of
    the 149 routes are expected to miss; that is a documented blind spot, not a
    regression, so this warns rather than fails. A strictly-failing variant
    belongs in the exemption file once models.dev closes the gap.
    """
    generator = _load_generator()
    known = resolved_ids(load_catalog())

    missing = sorted(
        route
        for route in litellm_route_models()
        if generator.strip_author(_ROUTE_SUFFIX.sub("", route)) not in known
    )

    assert missing, (
        "every litellm route now resolves — promote this check to a failure, or "
        "record the remaining blind spots in config/model-catalog-exemptions.json"
    )
    with pytest.warns(UserWarning, match="litellm route"):
        for route in missing:
            warnings.warn(
                f"litellm route {route} has no models.dev catalog entry", UserWarning, stacklevel=1
            )
