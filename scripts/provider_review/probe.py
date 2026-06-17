# scripts/provider_review/probe.py
"""Step 1 of provider review: live-probe each configured provider.

Sends a minimal prompt via the OpenAI-compatible API using each provider's
base_url and the corresponding GitHub secret. Records success/failure/latency.

Usage:
    python scripts/provider_review/probe.py
    # writes /tmp/review/probe-results.json
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

PROBE_PROMPT = "Reply with the single word: ok"
PROBE_MAX_TOKENS = 10
PROBE_TIMEOUT = 30

# Base URLs and credentials for each probeable provider.
# api_key_env: the GitHub org secret that holds the key.
PROVIDERS: dict[str, dict] = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-2.5-flash",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_env": "CEREBRAS_API_KEY",
        "model": "llama-3.3-70b",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "model": "mistral-small-latest",
    },
    "nvidia_nim": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "model": "meta/llama-3.3-70b-instruct",
    },
    "ollama_cloud": {
        "base_url": "https://ollama.com/v1",
        "api_key_env": "OLLAMA_API_KEY",
        "model": "rnj-1:cloud",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
    },
    "github_models": {
        "base_url": "https://models.inference.ai.azure.com",
        "api_key_env": "GITHUB_TOKEN",
        "model": "gpt-4o-mini",
    },
}


def probe_provider(name: str, config: dict) -> dict:
    """Probe a single provider. Returns a result dict; never raises."""
    api_key = os.environ.get(config["api_key_env"], "").strip()
    probed_at = datetime.now(timezone.utc).isoformat()

    if not api_key:
        return {
            "provider": name,
            "status": "skipped",
            "reason": f"{config['api_key_env']} not set",
            "latency_ms": None,
            "error": None,
            "probed_at": probed_at,
        }

    client = OpenAI(api_key=api_key, base_url=config["base_url"])
    start = time.monotonic()
    try:
        client.chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": PROBE_PROMPT}],
            max_tokens=PROBE_MAX_TOKENS,
            timeout=PROBE_TIMEOUT,
        )
        latency_ms = round((time.monotonic() - start) * 1000)
        return {
            "provider": name,
            "status": "ok",
            "reason": None,
            "latency_ms": latency_ms,
            "error": None,
            "probed_at": probed_at,
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000)
        return {
            "provider": name,
            "status": "failed",
            "reason": None,
            "latency_ms": latency_ms,
            "error": str(exc),
            "probed_at": probed_at,
        }


def run_probes(output_path: str = "/tmp/review/probe-results.json") -> list[dict]:
    """Probe all providers and write results JSON. Always exits 0."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    results = [probe_provider(name, cfg) for name, cfg in PROVIDERS.items()]
    Path(output_path).write_text(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    results = run_probes()
    for r in results:
        status = r["status"].upper()
        latency = f"{r['latency_ms']}ms" if r["latency_ms"] is not None else "—"
        suffix = f" ({r['error'][:80]})" if r.get("error") else (f" — {r['reason']}" if r.get("reason") else "")
        print(f"  {status:7} {r['provider']:<15} {latency}{suffix}")
