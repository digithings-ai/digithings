#!/usr/bin/env python3
"""Smoke-test each LLM provider key configured for the research pipeline.

Run after adding keys to .env or after setting GitHub Actions secrets locally:

    source .env && python scripts/validate-provider-keys.py

Exit code 0 = all configured providers responded OK.
Exit code 1 = at least one configured provider failed (key missing or API error).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)

# The provider table is config, not code (#5029): which providers to smoke-test
# and which model each sends are facts about the providers. Only the
# env-conditional wiring stays here, because env state is not config.
REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_CONFIG_PATH = Path(os.environ.get("DIGI_CONFIG_PATH") or REPO_ROOT / "config") / (
    "provider-key-checks.json"
)


def _load_providers() -> dict[str, dict]:
    """Read config/provider-key-checks.json into the shape test_provider() expects.

    Fail-loud: an empty provider set would print "all configured providers OK",
    which is the most dangerous possible output from a validation script.
    """
    try:
        raw = json.loads(CHECK_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"provider check table missing: {CHECK_CONFIG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"provider check table is not valid JSON: {CHECK_CONFIG_PATH}") from exc
    providers = raw.get("providers") if isinstance(raw, dict) else None
    if not isinstance(providers, dict) or not providers:
        raise RuntimeError(
            f"provider check table has no non-empty 'providers' object: {CHECK_CONFIG_PATH}"
        )
    required = {"label", "base_url", "api_key_env", "model_default"}
    missing = sorted(n for n, c in providers.items() if not required <= set(c))
    if missing:
        raise RuntimeError(f"provider check entries missing {sorted(required)}: {missing}")
    return providers


def _apply_env_overrides(providers: dict[str, dict]) -> dict[str, dict]:
    """Overlay the environment-dependent wiring that config deliberately omits.

    ollama is the only one: the house proxy is reached by pointing
    ``OPENAI_API_BASE`` at it, and CI maps ``secrets.OLLAMA_API_KEY`` onto
    ``OPENAI_API_KEY``, so a local shell with only OPENAI_API_KEY set must still
    find a key. Both are properties of the environment, not of the provider.
    """
    out = {name: dict(cfg) for name, cfg in providers.items()}
    if "ollama" in out:
        out["ollama"]["base_url"] = os.environ.get("OPENAI_API_BASE", out["ollama"]["base_url"])
        if not os.environ.get("OLLAMA_API_KEY") and os.environ.get("OPENAI_API_KEY"):
            out["ollama"]["api_key_env"] = "OPENAI_API_KEY"
    return out


PROVIDERS = _apply_env_overrides(_load_providers())

TEST_MESSAGES = [{"role": "user", "content": "Reply with exactly: OK"}]


def test_provider(name: str, cfg: dict, *, strict: bool = False) -> bool:
    label = cfg["label"]
    api_key = os.environ.get(cfg["api_key_env"], "").strip()
    if not api_key:
        if cfg.get("required"):
            print(f"  FAIL  {label}: {cfg['api_key_env']} not set (required)")
            return False
        print(f"  SKIP  {label}: {cfg['api_key_env']} not set (optional — keys not yet configured)")
        return False if strict else True

    model = os.environ.get(cfg.get("model_env", ""), "").strip() or cfg["model_default"]
    try:
        client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
        r = client.chat.completions.create(
            model=model,
            messages=TEST_MESSAGES,
            temperature=0.0,
            max_tokens=16,
        )
        content = (r.choices[0].message.content or "").strip() if r.choices else ""
        print(f"  OK    {label} ({model}): {content!r}")
        return True
    except Exception as exc:
        if cfg.get("required"):
            print(f"  FAIL  {label} ({model}): {exc}")
            return False
        print(f"  WARN  {label} ({model}): {exc}")
        return False if strict else True


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--strict",
        "--fail-on-skip",
        action="store_true",
        dest="strict",
        help="treat SKIP/WARN (optional providers) as failure (#3787)",
    )
    args = ap.parse_args()
    print("research provider validation\n")
    results = []
    for name, cfg in PROVIDERS.items():
        results.append(test_provider(name, cfg, strict=args.strict))

    print()
    failures = results.count(False)
    if failures:
        print(f"RESULT: {failures} provider(s) failed — see output above.")
        print("See docs/research/token-budget.md for setup instructions.")
        return 1
    print("RESULT: all configured providers OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
