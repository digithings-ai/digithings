#!/usr/bin/env python3
"""Normalize models.dev into one vendored provider-model catalog (#4994).

Every part of the stack used to answer "what models does this provider have?"
its own way: digichat hardcoded five upstream URLs, ``config/litellm.yaml`` pinned
149 routes by hand, ``digillm/client.py`` carried four hand-kept constants, and
``scripts/refresh_model_routes.py`` fetched models.dev into a human menu nobody
read. This script is the one place a model list enters the repo.

Two artifacts come out of a single fetch:

``config/model-catalog.json``
    Canonical, diffable, and reviewable -- a PR that refreshes it shows exactly
    which models, prices, and capabilities moved. Python consumers (tests,
    digiquant, digigraph) read it.

``apps/digichat/src/lib/model-catalog.generated.ts``
    Generated because digichat is a Next standalone bundle whose image ships only
    ``apps/digichat/config`` (``apps/digichat/Dockerfile``); repo-root ``config/``
    is not in it, so a runtime ``readFile`` is not available and a runtime fetch
    would put every BFF instance behind a 5.7 MB CDN pull with no auth.

Both are **generated files -- never hand-edit them.** Refresh with
``make model-catalog``; drift is caught by ``make model-catalog-check``, which is
network-free and is what CI runs.

The catalog is metadata only. It deliberately carries no base URL, env var name,
or npm package: those are routing and credential-plumbing concerns that live in
``config/byok-providers.json`` and must stay auditable there, and a URL in a
module the browser bundle imports would be an SSRF surface.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The two generated artifacts and the hand-maintained exemption list.
CATALOG_JSON_PATH = REPO_ROOT / "config" / "model-catalog.json"
TS_MODULE_PATH = REPO_ROOT / "apps" / "digichat" / "src" / "lib" / "model-catalog.generated.ts"
EXEMPTIONS_PATH = REPO_ROOT / "config" / "model-catalog-exemptions.json"

#: The upstream body is ~5.7 MB, so the default is sized for a slow pull rather
#: than a fast one; callers pass a larger one for a cold cache.
DEFAULT_FETCH_TIMEOUT_SECONDS = 30.0

#: The models.dev provider keys this repo vendors. Sorted so ``_meta.providers``
#: and every downstream diff are stable. models.dev carries 226 providers;
#: shipping all of them would make the vendored file 5.7 MB for models this repo
#: cannot route. Local ``ollama`` is absent by nature (per-machine, not a catalog),
#: and cheaperinference / litellm-proxy are OpenAI-compatible endpoints rather
#: than curated model sets -- both are out of scope per the spec.
CATALOG_PROVIDERS: tuple[str, ...] = (
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
)

#: Evaluated in this order, first match wins. Mirrors ``tierFor()`` in
#: ``apps/digichat/src/lib/openrouter-catalog.ts:70-75`` so the live OpenRouter
#: buckets and the catalog buckets put a model in the same place.
TIER_ORDER = ("free", "flagship", "opensource")

#: BYOK provider id (``config/byok-providers.json``) -> models.dev provider key.
#: Three of the nine differ in spelling, which is the whole reason the map exists:
#: our picker says ``gemini``, models.dev says ``google``; we say ``together``,
#: it says ``togetherai``; we say ``fireworks``, it says ``fireworks-ai``.
#: Lookups return ``None`` for an unmapped id rather than a default -- coercing an
#: unknown provider is how a model id ends up validated against the wrong list.
BYOK_PROVIDER_TO_CATALOG_PROVIDER: dict[str, str] = {
    "anthropic": "anthropic",
    "deepseek": "deepseek",
    "fireworks": "fireworks-ai",
    "gemini": "google",
    "groq": "groq",
    "openai": "openai",
    "openrouter": "openrouter",
    "together": "togetherai",
    "xai": "xai",
}


def byok_provider_to_catalog_provider(byok_id: str) -> str | None:
    """The models.dev provider key behind a BYOK provider id, or ``None``."""
    return BYOK_PROVIDER_TO_CATALOG_PROVIDER.get(byok_id)


def strip_author(model_id: str) -> str:
    """Drop everything up to and including the first ``/``.

    ``gemini/gemini-2.5-flash`` -> ``gemini-2.5-flash``; ``gpt-4o`` is unchanged.
    BYOK fallback ids are author-prefixed for OpenRouter and bare for a
    first-party provider, so a coverage check has to compare on the suffix.
    """
    return model_id.split("/", 1)[1] if "/" in model_id else model_id

#: Carried over from ``FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M``
#: (``openrouter-catalog.ts:34``). A price floor rather than a model-name list is
#: what lets the catalog derive the tier instead of maintaining a second name list
#: that drifts.
FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M = 3.0

SCHEMA_VERSION = 1
MODELS_DEV_CATALOG_URL = "https://models.dev/catalog.json"
CATALOG_SOURCE = "models.dev"

#: The normalized key set. A new key is a schema change (bump SCHEMA_VERSION),
#: pinned by ``tests/scripts/test_refresh_model_catalog.py``.
ENTRY_FIELDS = (
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
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _positive_int(value: object) -> int | None:
    """A positive integer, or ``None`` for absent, non-numeric, or zero."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    # models.dev ships limit.context == 0 for image models (openai
    # chatgpt-image-latest), which is "unknown", not "a zero-length window".
    return int(value) if int(value) > 0 else None


def _cost_usd_per_million(cost: object, key: str) -> float | None:
    """A non-negative per-million-token price, or ``None`` when absent."""
    if not isinstance(cost, dict):
        return None
    raw = cost.get(key)
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return None
    return float(raw) if raw >= 0 else None


def _optional_bool(raw: object) -> bool | None:
    """``True``/``False`` when upstream said so, ``None`` when it did not."""
    return raw if isinstance(raw, bool) else None


def _modalities(modalities: object, side: str) -> list[str]:
    if not isinstance(modalities, dict):
        return []
    values = modalities.get(side)
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]


def derive_tier(cost_in: float | None, cost_out: float | None, open_weights: bool) -> str | None:
    """First match wins, in the same order as ``tierFor()``.

    A missing cost can never yield ``free`` or ``flagship``: models.dev omits
    ``cost`` on 8 of xai's 13 rows and 10 of groq's 16, so a ``None``-as-``0``
    reading would mis-bucket a third of two providers' models as free. Unknown
    prices degrade to no tier, which lands the model in the unfiltered ``all``
    bucket rather than in a wrong one.
    """
    if cost_in is not None and cost_out is not None and cost_in == 0 and cost_out == 0:
        return "free"
    if cost_in is not None and cost_in >= FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M:
        return "flagship"
    if open_weights:
        return "opensource"
    return None


def _normalize_model(raw: object, fallback_id: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    model_id = raw.get("id")
    if not isinstance(model_id, str) or not model_id:
        model_id = fallback_id
    name = raw.get("name")
    cost = raw.get("cost") if isinstance(raw.get("cost"), dict) else {}
    limit = raw.get("limit") if isinstance(raw.get("limit"), dict) else {}
    modalities = raw.get("modalities")
    modalities_input = _modalities(modalities, "input")

    cost_in = _cost_usd_per_million(cost, "input")
    cost_out = _cost_usd_per_million(cost, "output")
    open_weights = bool(raw.get("open_weights") is True)

    return {
        "id": model_id,
        "label": name if isinstance(name, str) and name else model_id,
        "cost_input_usd_per_million": cost_in,
        "cost_output_usd_per_million": cost_out,
        "context_window": _positive_int(limit.get("context")),
        "max_output_tokens": _positive_int(limit.get("output")),
        "modalities_input": modalities_input,
        "modalities_output": _modalities(modalities, "output"),
        "tool_call": _optional_bool(raw.get("tool_call")),
        "structured_output": _optional_bool(raw.get("structured_output")),
        "reasoning": _optional_bool(raw.get("reasoning")),
        # Derived rather than copied: models.dev's `attachment` is true for some
        # models whose input modalities do not include images, and a capability
        # filter wants the modality, not the marketing flag.
        "vision": "image" in modalities_input,
        "attachment": _optional_bool(raw.get("attachment")),
        "open_weights": open_weights,
        "tier": derive_tier(cost_in, cost_out, open_weights),
    }


def normalize_catalog(payload: dict[str, Any], *, fetched_at: str | None = None) -> dict[str, Any]:
    """Turn a models.dev ``catalog.json`` body into the normalized catalog.

    Pure with respect to ``payload``: the same body always yields the same
    ``models`` block. ``fetched_at`` is provenance about the fetch rather than a
    property of the data, so it is injectable -- otherwise re-rendering the
    generated TypeScript module would produce a diff on every run.
    """
    providers = payload.get("providers")
    providers = providers if isinstance(providers, dict) else {}

    models: dict[str, list[dict[str, Any]]] = {}
    for provider in CATALOG_PROVIDERS:
        block = providers.get(provider)
        raw_models = block.get("models") if isinstance(block, dict) else None
        if not isinstance(raw_models, dict):
            # models.dev drops and re-adds providers as vendors change. An absent
            # provider normalizes to an empty list rather than aborting a refresh.
            models[provider] = []
            continue
        entries = [
            normalized
            for normalized in (_normalize_model(raw, model_id) for model_id, raw in raw_models.items())
            if normalized is not None
        ]
        models[provider] = sorted(entries, key=lambda entry: entry["id"])

    return {
        "_meta": {
            "schema_version": SCHEMA_VERSION,
            "source": CATALOG_SOURCE,
            "source_url": MODELS_DEV_CATALOG_URL,
            "fetched_at": fetched_at if isinstance(fetched_at, str) and fetched_at else _utc_now_iso(),
            "providers": list(CATALOG_PROVIDERS),
        },
        "models": models,
    }


class CatalogRefreshError(RuntimeError):
    """Raised when a refresh cannot produce a catalog worth committing."""


def fetch_catalog(timeout: float = DEFAULT_FETCH_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Fetch models.dev's ``catalog.json``.

    No auth, no retry, no caching: this is a manual/CI-invoked fetch whose
    result is committed, so a stale cache here would only hide upstream churn.
    The timeout is explicit on both the client and the request -- an unbounded
    pull of a 5.7 MB body is how a refresh job hangs with no operator signal.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(MODELS_DEV_CATALOG_URL, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise CatalogRefreshError(
            f"models.dev fetch failed ({type(exc).__name__}: {exc}). "
            f"Re-run when the endpoint is reachable, or refresh offline from the "
            f"committed catalog with --offline."
        ) from exc
    if not isinstance(payload, dict):
        raise CatalogRefreshError("models.dev returned a non-object body")
    return payload


def _ts_literal(value: Any, *, indent: int | None = None) -> str:
    """A JSON literal that is also a valid TypeScript expression.

    ``indent=None`` keeps small exports on one line; the big per-provider block
    is indented for review. Both are byte-stable for a given value, which is
    what makes ``--check`` a byte comparison.
    """
    return json.dumps(value, indent=indent, ensure_ascii=False)


def render_typescript_module(catalog: dict[str, Any]) -> str:
    """Render the digichat-facing TypeScript module for a normalized catalog.

    The module is data, not logic: each export is a plain JSON literal so a
    reader can diff it against ``config/model-catalog.json`` directly, and so a
    malformed artifact fails a test rather than a build.

    ``MODEL_CATALOG_META`` carries ``_meta`` verbatim, including ``fetched_at``.
    That is the only clock-derived value in the module, and it comes from the
    committed JSON rather than from a read here -- otherwise every
    ``--offline`` run would produce a diff.
    """
    meta = catalog.get("_meta") if isinstance(catalog.get("_meta"), dict) else {}
    models = catalog.get("models") if isinstance(catalog.get("models"), dict) else {}
    lines = [
        "// GENERATED FILE -- do not edit. Produced by scripts/refresh_model_catalog.py",
        "// (`make model-catalog`) from models.dev; validated by `make model-catalog-check`.",
        "// Source of truth: config/model-catalog.json. Edit the generator, not this file.",
        'import type { ModelCatalogEntry } from "./model-catalog";',
        "",
        f"export const MODEL_CATALOG_SCHEMA_VERSION = {_ts_literal(meta.get('schema_version'))};",
        "",
        f"export const MODEL_CATALOG_PROVIDERS = {_ts_literal(meta.get('providers'))} as const;",
        "",
        f"export const MODEL_CATALOG_META = {_ts_literal(meta, indent=2)} as const;",
        "",
        "export const MODEL_CATALOG_BYOK_PROVIDER_MAP: Record<string, string> = "
        f"{_ts_literal(BYOK_PROVIDER_TO_CATALOG_PROVIDER)};",
        "",
        "export const MODEL_CATALOG_BY_PROVIDER: Record<string, readonly ModelCatalogEntry[]> = "
        f"{_ts_literal(models, indent=2)};",
        "",
    ]
    return "\n".join(lines)


def write_artifacts(catalog: dict[str, Any], *, json_path: Path, ts_path: Path) -> None:
    """Write both artifacts, refusing to write an empty catalog.

    An upstream hiccup that yields no providers would otherwise overwrite a good
    catalog with nothing -- a diff that reads as 606 deliberate model deletions
    rather than as a failed fetch.
    """
    models = catalog.get("models") if isinstance(catalog.get("models"), dict) else {}
    if not any(models.values()):
        raise CatalogRefreshError(
            "refusing to write an empty catalog -- the fetch returned no models. "
            "Leaving the committed artifacts untouched."
        )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    ts_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ts_path.write_text(render_typescript_module(catalog), encoding="utf-8")


def _display(path: Path) -> str:
    """A repo-relative path when there is one, the raw path when there is not."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_committed_catalog() -> dict[str, Any]:
    if not CATALOG_JSON_PATH.is_file():
        raise CatalogRefreshError(
            f"{_display(CATALOG_JSON_PATH)} is missing -- run "
            f"`python3 scripts/refresh_model_catalog.py` first."
        )
    catalog = json.loads(CATALOG_JSON_PATH.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict):
        raise CatalogRefreshError("committed model-catalog.json is not an object")
    return catalog


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh the vendored provider-model catalog from models.dev (#4994)."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Re-render the TypeScript module from the committed JSON without fetching.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the committed artifacts without network access (CI drift guard).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_FETCH_TIMEOUT_SECONDS,
        help=f"Fetch timeout in seconds (default {DEFAULT_FETCH_TIMEOUT_SECONDS}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.check:
        return check_artifacts()

    if args.offline:
        catalog = _load_committed_catalog()
        TS_MODULE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TS_MODULE_PATH.write_text(render_typescript_module(catalog), encoding="utf-8")
        print(f"refresh-model-catalog: re-rendered {TS_MODULE_PATH.name} from the committed catalog")
        return 0

    catalog = normalize_catalog(fetch_catalog(timeout=args.timeout))
    write_artifacts(catalog, json_path=CATALOG_JSON_PATH, ts_path=TS_MODULE_PATH)
    total = sum(len(entries) for entries in catalog["models"].values())
    print(
        f"refresh-model-catalog: wrote {total} models across {len(catalog['models'])} providers "
        f"to {_display(CATALOG_JSON_PATH)} and {_display(TS_MODULE_PATH)}"
    )
    return 0


#: Provider-level and per-model keys that must never reach the artifacts. A base
#: URL in a module the browser bundle imports is an SSRF surface, and an env var
#: name is a credential-plumbing hint that belongs in config/byok-providers.json.
FORBIDDEN_KEYS = ("url", "api", "env", "npm", "doc")


def _resolved_ids(catalog: dict[str, Any]) -> set[str]:
    """Every catalogued id plus its author-stripped suffix."""
    resolved: set[str] = set()
    models = catalog.get("models") if isinstance(catalog.get("models"), dict) else {}
    for entries in models.values():
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                resolved.add(entry["id"])
                resolved.add(strip_author(entry["id"]))
    return resolved


def assert_invariants(catalog: dict[str, Any], *, exemptions_path: Path) -> list[str]:
    """Return every invariant the committed catalog violates; empty means clean.

    Each check is one line of output naming the offending path, so a red CI run
    says what to fix rather than that something is wrong. These are the checks
    that make the committed file trustworthy as a source of truth: a reviewer
    reading a diff can assume the schema held.
    """
    violations: list[str] = []

    if not isinstance(catalog, dict):
        return ["catalog is not an object"]

    meta = catalog.get("_meta") if isinstance(catalog.get("_meta"), dict) else {}
    models = catalog.get("models") if isinstance(catalog.get("models"), dict) else {}

    if meta.get("schema_version") != SCHEMA_VERSION:
        violations.append(
            f"_meta.schema_version is {meta.get('schema_version')!r}, expected {SCHEMA_VERSION}"
        )

    declared = meta.get("providers")
    if not isinstance(declared, list) or declared != sorted(declared):
        violations.append(f"_meta.providers is not sorted: {declared!r}")
    elif declared != list(CATALOG_PROVIDERS):
        violations.append(
            f"_meta.providers does not match CATALOG_PROVIDERS: {declared!r} != {list(CATALOG_PROVIDERS)!r}"
        )

    for provider in models:
        if provider not in declared if isinstance(declared, list) else True:
            violations.append(f"models.{provider} is not listed in _meta.providers")

    for provider, entries in models.items():
        if not isinstance(entries, list):
            violations.append(f"models.{provider} is not a list")
            continue
        ids = [e.get("id") for e in entries if isinstance(e, dict)]
        if len(ids) != len(set(ids)):
            violations.append(f"models.{provider} has a duplicate id")
        if ids != sorted(ids):  # type: ignore[operator]
            violations.append(f"models.{provider} entries are not sorted by id")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            where = f"models.{provider}[{entry.get('id')!r}]"
            for key in set(entry) & set(FORBIDDEN_KEYS):
                violations.append(f"{where} carries the routing key {key!r}")
            if set(entry) != set(ENTRY_FIELDS):
                violations.append(f"{where} key set does not match ENTRY_FIELDS")
            context = entry.get("context_window")
            if context is not None and (not isinstance(context, int) or context <= 0):
                violations.append(f"{where}.context_window is {context!r}, expected a positive int or null")
            for key in ("cost_input_usd_per_million", "cost_output_usd_per_million"):
                value = entry.get(key)
                if value is not None and (not isinstance(value, (int, float)) or value < 0):
                    violations.append(f"{where}.{key} is {value!r}, expected a non-negative number or null")
            for key in ("structured_output", "tool_call", "reasoning", "attachment"):
                if entry.get(key) not in (None, True, False):
                    violations.append(f"{where}.{key} is not tri-state")
            if entry.get("tier") not in (*TIER_ORDER, None):
                violations.append(f"{where}.tier is {entry.get('tier')!r}, not a known tier or null")

    violations.extend(_exemption_violations(catalog, exemptions_path))
    return violations


def _exemption_violations(catalog: dict[str, Any], exemptions_path: Path) -> list[str]:
    """Two rules: every exemption is justified, and no exemption is obsolete."""
    if not exemptions_path.is_file():
        return [f"{_display(exemptions_path)} is missing"]

    try:
        payload = json.loads(exemptions_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{_display(exemptions_path)} is not valid JSON: {exc}"]

    entries = payload.get("exemptions") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return [f"{_display(exemptions_path)} has no `exemptions` list"]

    resolved = _resolved_ids(catalog)
    violations: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            violations.append(f"exemptions[{index}] is not an object")
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id:
            violations.append(f"exemptions[{index}] has no id")
            continue
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            violations.append(f"exemption {model_id!r} has no non-empty reason")
        if model_id in resolved or strip_author(model_id) in resolved:
            violations.append(
                f"exemption {model_id!r} is no longer needed -- the catalog now resolves it"
            )
    return violations


def check_artifacts() -> int:
    """Validate the committed artifacts. Network-free by construction."""
    catalog = _load_committed_catalog()
    violations = assert_invariants(catalog, exemptions_path=EXEMPTIONS_PATH)
    for violation in violations:
        print(f"refresh-model-catalog: {_display(CATALOG_JSON_PATH)}: {violation}")

    if TS_MODULE_PATH.is_file():
        rendered = render_typescript_module(catalog)
        if TS_MODULE_PATH.read_text(encoding="utf-8") != rendered:
            violations.append(f"{_display(TS_MODULE_PATH)} is out of sync with the committed catalog")
            print(f"refresh-model-catalog: {violations[-1]}")
    else:
        violations.append(f"{_display(TS_MODULE_PATH)} is missing")
        print(f"refresh-model-catalog: {violations[-1]}")

    if not violations:
        print("refresh-model-catalog: OK — committed artifacts are in sync")
        return 0

    print(
        "refresh-model-catalog: DRIFT — fix the generator and re-run "
        "`python3 scripts/refresh_model_catalog.py --offline`"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())