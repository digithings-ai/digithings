#!/usr/bin/env python3
"""Smoke-test each LLM provider key configured for the Atlas pipeline.

Run after adding keys to .env or after setting GitHub Actions secrets locally:

    source .env && python scripts/validate-provider-keys.py

Exit code 0 = all configured providers responded OK.
Exit code 1 = at least one configured provider failed (key missing or API error).
"""

from __future__ import annotations

import os
import sys

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)

PROVIDERS = {
    "ollama": {
        "label": "Ollama Cloud",
        "base_url": os.environ.get("OPENAI_API_BASE", "https://ollama.com/v1"),
        "api_key_env": "OPENAI_API_KEY",
        "model_env": "OLLAMA_MODEL",
        "model_default": "qwen3.5:cloud",
        "required": True,
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model_default": "llama-3.1-8b-instant",
        "required": False,
    },
    "gemini": {
        "label": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model_default": "gemini-2.0-flash",
        "required": False,
    },
}

TEST_MESSAGES = [{"role": "user", "content": "Reply with exactly: OK"}]


def test_provider(name: str, cfg: dict) -> bool:
    label = cfg["label"]
    api_key = os.environ.get(cfg["api_key_env"], "").strip()
    if not api_key:
        if cfg.get("required"):
            print(f"  FAIL  {label}: {cfg['api_key_env']} not set (required)")
            return False
        print(f"  SKIP  {label}: {cfg['api_key_env']} not set (optional — keys not yet configured)")
        return True

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
        print(f"  FAIL  {label} ({model}): {exc}")
        return False


def main() -> int:
    print("Atlas provider validation\n")
    results = []
    for name, cfg in PROVIDERS.items():
        results.append(test_provider(name, cfg))

    print()
    failures = results.count(False)
    if failures:
        print(f"RESULT: {failures} provider(s) failed — see output above.")
        print("See docs/atlas/token-budget.md for setup instructions.")
        return 1
    print("RESULT: all configured providers OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
