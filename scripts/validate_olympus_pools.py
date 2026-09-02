#!/usr/bin/env python3
"""Endpoint capability smoke check for the Olympus OpenRouter model pools (#1622).

Model-page capability claims are not sufficient: a slug's *serving endpoints* must
actually accept function tools and strict ``json_schema``, or phase calls 404 or come
back empty (#987 mistral-small; #1006 llama-4-maverick). For every distinct bare slug
pooled in ``config/olympus_models.yaml`` (plus ``openrouter/`` pins in
``config/model_modes.yaml`` ``phase_models``), this script verifies:

1. **Endpoint metadata** (`GET /api/v1/models/{slug}/endpoints`): at least one endpoint
   lists ``tools`` and ``structured_outputs`` in ``supported_parameters``, and the max
   context among those endpoints is >= ``--min-context`` (default 64000 — the #1559
   synthesis budget floor).
2. **Live tool call**: a minimal chat completion carrying one function tool with
   ``provider.require_parameters`` — a 404 here is the #987 failure mode.
3. **Live strict-JSON call**: ``response_format`` ``json_schema`` with ``strict: true``;
   the body must be non-empty and parse as JSON with the requested key.

Requires ``OPENROUTER_API_KEY``. Without it the script prints a notice and exits 0 so
non-secret CI contexts skip gracefully. Live calls use ``max_tokens=2000``: a
reasoning-capable slug bills hidden ``reasoning_content`` out of the same budget as
the visible answer, and a tight cap (previously 64) can let reasoning consume the
whole thing, cutting the response off one character into the visible answer — which
reads identically to "model can't do strict JSON" (caught on
``google/gemini-3.7-flash``, which returned a bare ``"H"``). A ``reasoning: {"enabled":
false}`` field was tried as a more surgical fix and reverted: OpenRouter rejects it
outright with HTTP 400 ("Reasoning is mandatory for this endpoint and cannot be
disabled") on endpoints that treat reasoning as inherent (``gemini-3.7-flash``,
``grok-4.6``), and combined with ``provider.require_parameters`` below it also 404'd
four unrelated slugs that never declared ``reasoning`` as a supported parameter at
all (``deepseek/deepseek-chat``, ``llama-4-maverick``, ``gpt-4o``, ``gpt-4o-mini`` —
run 31840424733). Raising ``max_tokens`` instead adds no new parameter, so it can't
interact with ``require_parameters``, and works uniformly across reasoning-mandatory,
reasoning-optional, and non-reasoning slugs alike. The full sweep costs on the order
of a few cents — nine distinct bare slugs x two live calls each, several against
frontier-tier models at up to 2000 max_tokens.

Usage:
    OPENROUTER_API_KEY=... python3 scripts/validate_olympus_pools.py
    python3 scripts/validate_olympus_pools.py --metadata-only   # no live calls
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

API_BASE = "https://openrouter.ai/api/v1"
_RETRYABLE_STATUS = (429, 500, 502, 503)
_RETRY_DELAY_S = 5.0
# One retry on an empty 200-body, mirroring digillm's empty-completion self-heal —
# the production path tolerates a single transient empty, so the gate must too;
# a slug that returns empty twice still fails (z-ai/glm-5 flaked this way on run 2).
_EMPTY_RETRIES = 1

_TOOL = {
    "type": "function",
    "function": {
        "name": "record_answer",
        "description": "Record the answer to the question.",
        "parameters": {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    },
}

_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "SmokeAnswer",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    },
}


def collect_pool_slugs(config_dir: Path) -> list[str]:
    """Distinct bare OpenRouter slugs from olympus phase pools + model_modes pins.

    ``web_search_models`` are excluded: those are ``:online``/native-search variants used
    only by the grounding pre-pass and are never routed to tool or structured-output
    phases (they would legitimately fail this check).
    """
    slugs: set[str] = set()
    olympus = yaml.safe_load((config_dir / "olympus_models.yaml").read_text()) or {}
    for tier in (olympus.get("tiers") or {}).values():
        for pool in (tier.get("allowed_models") or {}).values():
            for model in pool or []:
                slugs.add(_bare_slug(model))
    modes = yaml.safe_load((config_dir / "model_modes.yaml").read_text()) or {}
    for model in (modes.get("phase_models") or {}).values():
        slugs.add(_bare_slug(str(model)))
    return sorted(s for s in slugs if s and ":online" not in s)


def _bare_slug(model: str) -> str:
    """Strip the ``openrouter/`` prefix so a pool entry matches the API's model id."""
    return model.removeprefix("openrouter/").strip()


def _request(client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """One retry on transient upstream statuses or timeouts; other statuses returned as-is.

    A timeout has to be retried separately from a retryable *status*: it raises out of
    `client.request` instead of returning a response, so it never reached the status check
    below. That made a single slow upstream call fail the whole sweep — `/models/{slug}/
    endpoints` exceeded the client's 60s timeout partway through run 30543907845, after
    seven slugs had already passed, and the gate went red with nothing wrong with the pools.
    The status path already tolerates one transient failure; a timeout is the same kind of
    upstream blip and gets the same single retry.
    """
    try:
        resp = client.request(method, url, **kwargs)
    except httpx.TimeoutException:
        time.sleep(_RETRY_DELAY_S)
        resp = client.request(method, url, **kwargs)
    if resp.status_code in _RETRYABLE_STATUS:
        time.sleep(_RETRY_DELAY_S)
        resp = client.request(method, url, **kwargs)
    return resp


def check_endpoints(client: httpx.Client, slug: str, min_context: int) -> str | None:
    """Return an error string, or None when the slug's endpoint metadata passes."""
    resp = _request(client, "GET", f"{API_BASE}/models/{slug}/endpoints")
    if resp.status_code != 200:
        return f"endpoints lookup HTTP {resp.status_code}"
    endpoints = (resp.json().get("data") or {}).get("endpoints") or []
    capable = [
        e
        for e in endpoints
        if {"tools", "structured_outputs"} <= set(e.get("supported_parameters") or [])
    ]
    if not capable:
        return f"no endpoint supports tools+structured_outputs ({len(endpoints)} endpoints)"
    max_ctx = max(int(e.get("context_length") or 0) for e in capable)
    if max_ctx < min_context:
        return f"capable endpoints max context {max_ctx} < required {min_context}"
    return None


def check_tools_call(client: httpx.Client, slug: str) -> str | None:
    """Return an error string, or None when a minimal function-tool call is accepted."""
    for attempt in range(_EMPTY_RETRIES + 1):
        if attempt:
            time.sleep(_RETRY_DELAY_S)
        resp = _request(
            client,
            "POST",
            f"{API_BASE}/chat/completions",
            json={
                "model": slug,
                "messages": [{"role": "user", "content": "Call record_answer with answer='ok'."}],
                "tools": [_TOOL],
                "max_tokens": 2000,
                "provider": {"require_parameters": True},
            },
        )
        if resp.status_code != 200:
            return f"tools call HTTP {resp.status_code}: {resp.text[:160]}"
        message = (resp.json().get("choices") or [{}])[0].get("message") or {}
        if message.get("tool_calls") or (message.get("content") or "").strip():
            return None
    return "tools call returned an empty body twice (no tool_calls, no content)"


def check_strict_json_call(client: httpx.Client, slug: str) -> str | None:
    """Return an error string, or None when strict json_schema output parses."""
    for attempt in range(_EMPTY_RETRIES + 1):
        if attempt:
            time.sleep(_RETRY_DELAY_S)
        resp = _request(
            client,
            "POST",
            f"{API_BASE}/chat/completions",
            json={
                "model": slug,
                "messages": [{"role": "user", "content": "Answer with the single word ok."}],
                "response_format": _JSON_SCHEMA,
                "max_tokens": 2000,
                "provider": {"require_parameters": True},
            },
        )
        if resp.status_code != 200:
            return f"json_schema call HTTP {resp.status_code}: {resp.text[:160]}"
        choice = (resp.json().get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        finish_reason = choice.get("finish_reason")
        if content.strip():
            break
    else:
        return "json_schema call returned an empty body twice"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        if finish_reason == "length":
            return f"json_schema output truncated at max_tokens (finish_reason=length); body: {content[:120]}"
        return f"json_schema output is not valid JSON ({exc}); body: {content[:120]}"
    if "answer" not in parsed:
        return f"json_schema output missing required key 'answer': {content[:120]}"
    return None


def main() -> int:
    """Collect pool slugs from config, gate each against the live endpoint checks, and report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-dir", default=os.environ.get("DIGI_CONFIG_PATH", "config"), type=Path
    )
    parser.add_argument(
        "--min-context",
        type=int,
        default=64_000,
        help="context floor for tools+structured_outputs endpoints (#1559 budget)",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="skip live completions; check endpoint metadata only",
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("OPENROUTER_API_KEY not set — skipping pool validation (nothing checked).")
        return 0

    slugs = collect_pool_slugs(args.config_dir)
    if not slugs:
        print(f"no pooled slugs found under {args.config_dir} — check --config-dir")
        return 1

    failures: dict[str, list[str]] = {}
    with httpx.Client(headers={"Authorization": f"Bearer {api_key}"}, timeout=60.0) as client:
        for slug in slugs:
            errors: list[str] = []
            for label, check in (
                ("endpoints", lambda s: check_endpoints(client, s, args.min_context)),
                ("tools", None if args.metadata_only else lambda s: check_tools_call(client, s)),
                (
                    "json_schema",
                    None if args.metadata_only else lambda s: check_strict_json_call(client, s),
                ),
            ):
                if check is None:
                    continue
                error = check(slug)
                if error:
                    errors.append(f"{label}: {error}")
            status = "PASS" if not errors else "FAIL"
            print(f"[{status}] {slug}" + ("".join(f"\n         - {e}" for e in errors)))
            if errors:
                failures[slug] = errors

    print(f"\n{len(slugs) - len(failures)}/{len(slugs)} pooled slugs passed.")
    if failures:
        print("FAILED slugs: " + ", ".join(sorted(failures)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
