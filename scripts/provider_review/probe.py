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

REPO_ROOT = Path(__file__).resolve().parents[2]

PROBE_PROMPT = "Reply with the single word: ok"
PROBE_MAX_TOKENS = 10
PROBE_TIMEOUT = 30

# The probe table is config, not code (#5029): which providers the weekly review
# probes, and which model each probe sends, are facts about the providers rather
# than facts about how to probe them. Same env-var convention as
# digigraph's llm_auth._resolve_byok_catalog_path — DIGI_CONFIG_PATH overrides the
# directory; without it the __file__-relative path keeps resolving to the repo's
# own config/ regardless of the process's working directory.
PROBE_CONFIG_DIR = Path(os.environ.get("DIGI_CONFIG_PATH") or REPO_ROOT / "config")
PROBE_CONFIG_PATH = PROBE_CONFIG_DIR / "provider-probes.json"


def _load_providers() -> dict[str, dict]:
    """Read config/provider-probes.json into the shape probe_provider() expects.

    Fail-loud, like llm_auth's catalog loader: a silently empty provider set
    would report "every provider failed" and read as an outage rather than as a
    missing file, which is the worse failure of the two.
    """
    try:
        raw = json.loads(PROBE_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"probe table missing: {PROBE_CONFIG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"probe table is not valid JSON: {PROBE_CONFIG_PATH}") from exc
    providers = raw.get("providers") if isinstance(raw, dict) else None
    if not isinstance(providers, dict) or not providers:
        raise RuntimeError(f"probe table has no non-empty 'providers' object: {PROBE_CONFIG_PATH}")
    missing = sorted(
        n for n, c in providers.items() if not {"base_url", "api_key_env", "model"} <= set(c)
    )
    if missing:
        raise RuntimeError(f"probe table entries missing base_url/api_key_env/model: {missing}")
    return providers


PROVIDERS: dict[str, dict] = _load_providers()


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
        suffix = (
            f" ({r['error'][:80]})"
            if r.get("error")
            else (f" — {r['reason']}" if r.get("reason") else "")
        )
        print(f"  {status:7} {r['provider']:<15} {latency}{suffix}")
