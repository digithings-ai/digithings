#!/usr/bin/env python3
"""Refresh a full provider model inventory: pricing, limits, capabilities.

Only providers with credentials/endpoints already configured are queried.
Capability + pricing shortlist comes from the public models.dev catalog;
live provider list endpoints record what each account can actually call.

The snapshot is a menu for humans: tier assignment (cheap/mid/flagship) and
per-phase model choice stay manual in ``config/digiquant_models.yaml``.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str
    prompt_price: float | None
    completion_price: float | None
    context_length: int
    supports_tools: bool
    supports_structured_output: bool


_PROVIDER_ENV_VARS: dict[str, tuple[str, ...]] = {
    "openrouter": ("OPENROUTER_API_KEY",),
    "litellm": ("LITELLM_API_BASE",),
    "cheaperinference": ("CHEAPERINFERENCE_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "together": ("TOGETHER_API_KEY",),
    "fireworks": ("FIREWORKS_API_KEY", "FIREWORKS_ACCOUNT_ID"),
    "ollama": ("OLLAMA_HOST",),
    "ollama-cloud": ("OLLAMA_API_KEY",),
}


def configured_providers(env: Mapping[str, str] | None = None) -> list[str]:
    """Return providers whose required env vars are all present and non-empty."""
    source = env if env is not None else os.environ
    configured: list[str] = []
    for provider, names in _PROVIDER_ENV_VARS.items():
        if all((source.get(name) or "").strip() for name in names):
            configured.append(provider)
    return configured


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_MODELS_DEV_CATALOG_URL = "https://models.dev/catalog.json"

# models.dev provider ids that differ from this repo's provider names.
_MODELS_DEV_PROVIDER_ALIASES = {
    "togetherai": "together",
    "fireworks-ai": "fireworks",
}

_DEFAULT_CHEAPERINFERENCE_API_BASE = "https://api.cheaperinference.com/v1"
_DEEPSEEK_API_BASE = "https://api.deepseek.com"
_GROQ_API_BASE = "https://api.groq.com/openai/v1"
_TOGETHER_API_BASE = "https://api.together.ai/v1"
_FIREWORKS_API_BASE = "https://api.fireworks.ai"
_OLLAMA_CLOUD_API_BASE = "https://ollama.com"


def _get_json(
    client: Any,
    url: str,
    api_key: str = "",
    params: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> Any:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = client.get(url, headers=headers, params=params, timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(f"model list lookup failed HTTP {response.status_code}: {url}")
    return response.json()


def fetch_openrouter_models(client: Any, api_key: str, timeout: float = 30.0) -> dict[str, Any]:
    """Fetch the OpenRouter model catalog, cheapest first."""
    payload = _get_json(
        client,
        _OPENROUTER_MODELS_URL,
        api_key=api_key,
        params={"sort": "pricing-low-to-high"},
        timeout=timeout,
    )
    return payload if isinstance(payload, dict) else {"data": payload}


def fetch_openai_models(client: Any, base_url: str, api_key: str = "") -> dict[str, Any]:
    """Fetch an OpenAI-compatible ``GET {base_url}/models`` catalog."""
    payload = _get_json(client, f"{base_url.rstrip('/')}/models", api_key=api_key)
    return payload if isinstance(payload, dict) else {"data": payload}


def fetch_ollama_tags(client: Any, base_url: str, api_key: str = "") -> dict[str, Any]:
    """Fetch an Ollama ``GET {base_url}/api/tags`` catalog (local or cloud)."""
    payload = _get_json(client, f"{base_url.rstrip('/')}/api/tags", api_key=api_key)
    return payload if isinstance(payload, dict) else {"models": payload}


def fetch_fireworks_models(client: Any, account_id: str, api_key: str) -> dict[str, Any]:
    """Fetch a Fireworks ``GET /v1/accounts/{account_id}/models`` catalog."""
    payload = _get_json(client, f"{_FIREWORKS_API_BASE}/v1/accounts/{account_id}/models", api_key)
    return payload if isinstance(payload, dict) else {"models": payload}


def fetch_models_dev_catalog(client: Any, timeout: float = 60.0) -> dict[str, Any]:
    """Fetch the public models.dev catalog (no auth): capability + pricing shortlist."""
    payload = _get_json(client, _MODELS_DEV_CATALOG_URL, timeout=timeout)
    return payload if isinstance(payload, dict) else {"providers": {}}


def _models_dev_price(value: Any) -> float | None:
    """Convert a models.dev per-million-token price to per-token dollars."""
    parsed = _as_float(value)
    return parsed / 1_000_000 if parsed is not None else None


def normalize_models_dev_catalog(
    payload: Mapping[str, Any], providers: list[str]
) -> list[ModelRoute]:
    """Normalize models.dev catalog entries for *providers* to routes."""
    wanted = set(providers)
    catalog_providers = payload.get("providers")
    if not isinstance(catalog_providers, Mapping):
        return []
    routes: list[ModelRoute] = []
    for catalog_id, provider_data in catalog_providers.items():
        ours = _MODELS_DEV_PROVIDER_ALIASES.get(str(catalog_id), str(catalog_id))
        if ours not in wanted or not isinstance(provider_data, Mapping):
            continue
        models = provider_data.get("models")
        if not isinstance(models, Mapping):
            continue
        for model_id, entry in models.items():
            if not isinstance(entry, Mapping):
                continue
            cost = entry.get("cost") if isinstance(entry.get("cost"), Mapping) else {}
            limit = entry.get("limit") if isinstance(entry.get("limit"), Mapping) else {}
            try:
                context_length = int(limit.get("context") or 0)
            except (TypeError, ValueError):
                context_length = 0
            routes.append(
                ModelRoute(
                    provider=ours,
                    model=str(model_id),
                    prompt_price=_models_dev_price(cost.get("input")),
                    completion_price=_models_dev_price(cost.get("output")),
                    context_length=context_length,
                    supports_tools=bool(entry.get("tool_call", False)),
                    supports_structured_output=bool(entry.get("structured_output", False)),
                )
            )
    return routes


def live_model_ids(payload: Mapping[str, Any]) -> list[str]:
    """Extract listed model ids from a live provider list payload."""
    entries = payload.get("data")
    id_key: str | None = "id"
    if not isinstance(entries, list):
        entries = payload.get("models")
        id_key = None  # ollama/fireworks style: "name", or "id" when present
    if not isinstance(entries, list):
        return []
    ids: list[str] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        name = entry.get(id_key) if id_key else (entry.get("id") or entry.get("name"))
        if name:
            ids.append(str(name))
    return ids


def build_inventory_snapshot(
    routes: list[ModelRoute],
    live: Mapping[str, list[str]],
    providers: list[str],
    min_context: int = 64000,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a full inventory snapshot: every catalog route plus live ids.

    Tier assignment stays manual (``config/digiquant_models.yaml``) — this
    snapshot is the menu humans choose from, not an auto-picker.
    """
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "providers": sorted(providers),
        "min_context": min_context,
        "source": "models.dev catalog + live provider lists",
        "routes": [asdict(route) for route in routes],
        "live": {provider: sorted(ids) for provider, ids in live.items()},
    }


def _price_per_million(price_per_token: float | None) -> str:
    if price_per_token is None:
        return "n/a"
    return f"{price_per_token * 1_000_000:.2f}"


def _is_listed_live(model: str, live_ids: set[str]) -> bool:
    """True when *model* matches a live id exactly or by trailing path segment.

    Catalog ids and live list ids use different namespaces on some providers
    (Fireworks catalog ids are ``accounts/…`` paths while live ids are bare
    names), so compare trailing segments too.
    """
    if model in live_ids:
        return True
    tail = model.rsplit("/", 1)[-1]
    return any(tail == live_id.rsplit("/", 1)[-1] for live_id in live_ids)


def render_table(routes: list[ModelRoute], live: Mapping[str, list[str]]) -> str:
    """Render routes as a human-readable pricing/capability table grouped by provider."""
    lines = ["provider | model | $/1M in | $/1M out | ctx | tools | json | live"]
    by_provider: dict[str, list[ModelRoute]] = {}
    for route in routes:
        by_provider.setdefault(route.provider, []).append(route)
    for provider in sorted(by_provider):
        live_ids = set(live.get(provider, []))
        for route in sorted(by_provider[provider], key=lambda r: r.model):
            lines.append(
                f"{provider} | {route.model} | {_price_per_million(route.prompt_price)} | "
                f"{_price_per_million(route.completion_price)} | {route.context_length} | "
                f"{'yes' if route.supports_tools else 'no'} | "
                f"{'yes' if route.supports_structured_output else 'no'} | "
                f"{'yes' if _is_listed_live(route.model, live_ids) else 'no'}"
            )
    return "\n".join(lines)


def write_snapshot(snapshot: Mapping[str, Any], out: Path) -> Path:
    """Write a snapshot mapping as JSON; return the output path."""
    out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return out


_REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None, client: Any | None = None) -> int:
    """Fetch configured provider catalogs and write a snapshot file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help="Snapshot output path")
    parser.add_argument("--min-context", type=int, default=64000)
    parser.add_argument(
        "--strict",
        "--fail-on-skip",
        action="store_true",
        dest="strict",
        help="exit 1 when no providers are configured (nothing refreshed) (#3787)",
    )
    args = parser.parse_args(argv)

    providers = configured_providers()
    if not providers:
        print("no providers configured; skipping model-route refresh")
        return 1 if args.strict else 0

    payloads: dict[str, Mapping[str, Any]] = {}
    live: dict[str, list[str]] = {}
    http_client = client
    if http_client is None:
        import httpx

        http_client = httpx.Client(timeout=30.0)
    env = os.environ
    openai_bases = {
        "litellm": (env.get("LITELLM_API_BASE") or "").strip(),
        "cheaperinference": (
            (env.get("CHEAPERINFERENCE_API_BASE") or "").strip()
            or _DEFAULT_CHEAPERINFERENCE_API_BASE
        ),
        "deepseek": _DEEPSEEK_API_BASE,
        "groq": _GROQ_API_BASE,
        "together": _TOGETHER_API_BASE,
    }
    openai_keys = {
        "litellm": "LITELLM_API_KEY",
        "cheaperinference": "CHEAPERINFERENCE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "groq": "GROQ_API_KEY",
        "together": "TOGETHER_API_KEY",
    }
    if "openrouter" in providers:
        payloads["openrouter"] = fetch_openrouter_models(
            http_client, api_key=(env.get("OPENROUTER_API_KEY") or "").strip()
        )
    for provider in ("litellm", "cheaperinference", "deepseek", "groq", "together"):
        if provider in providers:
            payloads[provider] = fetch_openai_models(
                http_client,
                base_url=openai_bases[provider],
                api_key=(env.get(openai_keys[provider]) or "").strip(),
            )
    if "fireworks" in providers:
        payloads["fireworks"] = fetch_fireworks_models(
            http_client,
            account_id=(env.get("FIREWORKS_ACCOUNT_ID") or "").strip(),
            api_key=(env.get("FIREWORKS_API_KEY") or "").strip(),
        )
    if "ollama" in providers:
        payloads["ollama"] = fetch_ollama_tags(
            http_client, base_url=(env.get("OLLAMA_HOST") or "").strip()
        )
    if "ollama-cloud" in providers:
        payloads["ollama-cloud"] = fetch_ollama_tags(
            http_client,
            base_url=_OLLAMA_CLOUD_API_BASE,
            api_key=(env.get("OLLAMA_API_KEY") or "").strip(),
        )
    for provider, payload in payloads.items():
        live[provider] = live_model_ids(payload)

    catalog = fetch_models_dev_catalog(http_client)
    routes = normalize_models_dev_catalog(catalog, providers)
    snapshot = build_inventory_snapshot(routes, live, providers, min_context=args.min_context)
    if args.out:
        out = Path(args.out)
    else:
        today = datetime.now(timezone.utc).date().isoformat()
        out = _REPO_ROOT / "reports" / f"model_routes_{today}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_snapshot(snapshot, out)
    print(f"wrote {len(routes)} routes across {len(providers)} providers to {out}")
    print(render_table(routes, live))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
