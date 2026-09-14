# Agent Guide: digillm

## Purpose

digillm is the **single home for LLM client / API-wrapper / tooling code** in the
monorepo: a standalone, **provider-agnostic** OpenAI-compatible client with
routing, retry/backoff, response caching, the tool-calling loop, structured
output, and strict provider telemetry. It has **no FastAPI / service coupling**
and no hard dependency on `digismith`; LiteLLM is the house upstream swap layer
via `OPENAI_API_BASE`, not an in-package assumption.

---

## Read First

In this order, before writing any code:

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — module map, public API, telemetry
   contracts, MCP hosting, and non-goals.
2. [`../AGENTS.md`](../AGENTS.md) — non-negotiable stack-wide rules.
3. [`digigraph/llm_client.py`](../digigraph/src/digigraph/llm_client.py) — the
   primary in-process consumer (grounding prompts and search tooling live
   *there*, not here).

---

## Pre-Flight Checklist

Before making any change to `digillm/`:

- [ ] Read `ARCHITECTURE.md` — Module Map, Public API, and Non-goals.
- [ ] Run `pytest digillm/tests -v --tb=short` — passes before and after.
- [ ] Run `ruff check digillm/src digillm/tests && ruff format --check digillm/src digillm/tests`
      — zero errors.
- [ ] Confirm **`import digillm` stays free of `fastapi` / `Request`** and of any
      provider-specific search module.
- [ ] Confirm new result data is a Pydantic v2 model / TypedDict in `types.py`,
      never a bare `dict`.
- [ ] Confirm there is **no fallback chain**: provider errors surface fail-fast.
- [ ] Confirm `[modes]` / `[trace]` / `[mcp]` stay optional — the base package
      (`openai` + `pydantic`) must install and function without them.

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **Hard deps are `openai>=1.0` + `pydantic>=2` only.** YAML (`[modes]`),
  LangSmith (`[trace]`), and MCP (`[mcp]`) are opt-in extras; never move them to
  `dependencies`.
- **No FastAPI, no `Request` objects, no service coupling.** digigraph imports
  `digillm` in-process; digillm must never import digigraph back.
- **No vendor search tooling.** No OpenRouter web-search, Exa, xAI Live Search,
  or Responses-API helpers. Grounding prompts belong to consumers; digillm owns
  routing + the tool loop only.
- **Fail-fast, no fallback chain.** A provider error propagates; do not add a
  silent model/provider fallback.
- **BYOK / proxy overrides are context-local.** Use the `overrides.py`
  contextvars and their reset helpers / context managers; never leak a
  per-request key into process-global state.
- **Telemetry is a sink, not a side effect.** `emit_telemetry` is fail-soft and
  must never abort caller work; prompts, responses, search text, API keys, and
  raw exceptions are never fields on a contract (only a sanitized exception
  type).
- **MCP hosting is loopback-only.** `python -m digillm.mcp_server` defaults to
  `127.0.0.1:8768` (`DIGILLM_MCP_PORT` override, `--stdio` for Claude Desktop).
  There is intentionally no supervisord program, stack slot, or Worker route.

---

## Anti-Patterns (do not do these here)

- ❌ Adding a provider-specific search / grounding branch (`openrouter_web_search`,
  `search_parameters`, Responses-API helpers, provider `extra_body` dials).
- ❌ `import fastapi` or accepting a Starlette `Request` anywhere in the package.
- ❌ Adding a required dependency on `digismith`, `pyyaml`, or `mcp`.
- ❌ Returning bare `dict`s from public functions (use `types.py`).
- ❌ Introducing a retry/fallback chain that hides a provider failure.
- ❌ Writing a per-request BYOK/proxy key into module globals instead of the
  contextvars.
- ❌ Leaking prompts, responses, keys, or raw exception text into telemetry
  records.
- ❌ `.md` edits via `ruff format` — Markdown is not source (see root `ruff.toml`).

---

## Test Commands

```bash
# Full suite (offline; every provider call is monkeypatched).
pytest digillm/tests -v --tb=short

# Unit-marked subset only (the suite is marked `unit` module-wide).
pytest digillm/tests -m unit -q

# Single file
pytest digillm/tests/test_fail_fast.py -v

# Lint + format
ruff check digillm/src digillm/tests && ruff format --check digillm/src digillm/tests

# Base library installs with no optional extras
pip install -e digillm/ --dry-run
```

> CI gate: [`.github/workflows/test-digillm.yml`](../.github/workflows/test-digillm.yml),
> wired into `ci.yml`. It installs from the committed `uv.lock` (`uv sync --frozen
> --all-packages --all-extras`) and runs ruff + the unfiltered suite.
>
> The suite is mostly `unit`-marked (`pytestmark = pytest.mark.unit` in
> `test_byok_isolation.py`, `test_digillm.py`, `test_fail_fast.py`, and
> `test_provider_telemetry.py`, plus `@pytest.mark.unit` on two tests in
> `test_mcp_server.py`), so `-m unit` selects most of it. The tests it excludes are
> the wholly unmarked `test_cheaperinference_routing.py` and
> `test_web_search_usage_kind.py` modules, plus the five unmarked cases in
> `test_mcp_server.py`. The workflow comment claiming "no test
> in digillm/tests carries the `unit` marker" is stale — do not edit workflows from
> this docs PR; correct that comment when the workflow is next touched.

---

## More

The full module map, public API, telemetry contracts, MCP hosting notes, and
design rationale live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc
whenever you change an interface or behavior.
