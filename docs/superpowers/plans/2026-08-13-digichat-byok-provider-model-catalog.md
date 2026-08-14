# DigiChat BYOK Provider & Model Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the BYOK picker's three independently-hardcoded provider lists with one JSON catalog, add a live OpenRouter model catalog with price-derived tiers + a custom starred set, extend live model lists to OpenAI/Anthropic/Gemini, add x.ai as a 5th provider, and add non-secret provider/model persistence across sessions.

**Architecture:** `config/byok-providers.json` becomes the single source of truth for which providers exist; `digigraph` loads it directly, the frontend keeps a hand-written TS mirror kept honest by a CI cross-check test. OpenRouter's public (unauthenticated) model catalog is fetched via a new BFF route and bucketed into tiers by a pure function using each model's own live pricing data — not a hand-maintained marker list. The BYOK key itself stays session-memory-only; only the non-secret provider+model *choice* persists, via a plain client-side cookie.

**Tech Stack:** TypeScript, Next.js App Router (route handlers), Vitest, React (`"use client"` components), Python 3.12 for the digigraph half.

## Global Constraints

- TypeScript strict; `npm run lint` and `npm run build` (typecheck) both clean before any task is considered done.
- Vitest for all new/modified frontend tests; co-locate `route.test.ts` beside `route.ts`, `*.test.ts` beside the module it tests — matches this repo's existing convention.
- Ruff-compliant Python (line length 100) for the digigraph half; tests live at `tests/dg/` (repo-root-relative).
- Never put a real-looking API key in a test — use obviously-fake strings that still pass format validation (`sk-test-…`, `sk-or-v1-test-…`), matching existing test fixtures.
- This plan spans **two module branches**: the frontend/catalog-JSON tasks are `component:digichat` (two-hop: `task/201-slug` → `module/digichat` → `develop`); the digigraph catalog-loader task is `component:digigraph` (its own two-hop). Check staleness before branching either: `git fetch origin && git rev-list --count origin/module/digichat..origin/develop` (93 behind as of the design spec's writing — re-check, it moves fast) and the same for `module/digigraph` (3 behind). Sync via a `chore/sync-*` PR into the stale module branch first.
- `llm_auth.py` changes are auth-adjacent per CLAUDE.md's human-gate rule — plan for explicit review before merge regardless of `make score`.
- Design reference: [`docs/superpowers/specs/2026-08-13-digichat-byok-model-catalog-design.md`](../specs/2026-08-13-digichat-byok-model-catalog-design.md).

---

### Task 1: `config/byok-providers.json` — the canonical catalog (4 providers, no behavior change)

**Files:**
- Create: `config/byok-providers.json`

**Interfaces:**
- Consumes: nothing.
- Produces: the JSON catalog — consumed by Task 2 (digigraph loader) and Task 4 (frontend cross-check test).

- [ ] **Step 1: Create the file**

```json
[
  {
    "id": "openrouter",
    "label": "OpenRouter",
    "keyPrefix": "sk-or-",
    "baseUrl": "https://openrouter.ai/api/v1",
    "requiresModel": true,
    "fallbackModels": [
      "openai/gpt-4o-mini",
      "openai/gpt-4o",
      "anthropic/claude-sonnet-4",
      "google/gemini-2.0-flash"
    ]
  },
  {
    "id": "openai",
    "label": "OpenAI",
    "keyPrefix": "sk-",
    "baseUrl": "https://api.openai.com/v1",
    "requiresModel": false,
    "fallbackModels": ["gpt-4o-mini", "gpt-4o", "o4-mini"]
  },
  {
    "id": "anthropic",
    "label": "Anthropic",
    "keyPrefix": "sk-ant-",
    "baseUrl": "https://api.anthropic.com/v1",
    "requiresModel": true,
    "fallbackModels": [
      "claude-sonnet-4-20250514",
      "claude-haiku-4-20250514",
      "claude-opus-4-20250514"
    ]
  },
  {
    "id": "gemini",
    "label": "Gemini",
    "keyPrefix": "AI",
    "baseUrl": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "requiresModel": true,
    "fallbackModels": [
      "gemini/gemini-2.0-flash",
      "gemini/gemini-2.5-flash",
      "gemini/gemini-2.5-pro"
    ]
  }
]
```

This must exactly match today's shipped provider set (openai/openrouter/anthropic/gemini) and today's model presets, byte-for-byte in meaning — Task 2 depends on zero behavior change from this file alone.

- [ ] **Step 2: Validate it's well-formed JSON**

Run: `python3 -c "import json; d = json.load(open('config/byok-providers.json')); print(len(d), 'entries')"`
Expected: `4 entries`

- [ ] **Step 3: Commit**

```bash
git add config/byok-providers.json
git commit -m "feat(config): byok-providers.json catalog (4 providers, matches shipped state)"
```

---

### Task 2: digigraph — `llm_auth.py` loads the catalog instead of a hardcoded dict

**Files:**
- Modify: `digigraph/src/digigraph/llm_auth.py:33-47`
- Test: `tests/dg/test_llm_auth.py` (all existing tests in `TestByokProviderGuard`/`TestByokGuardOverHttp` must pass **unchanged** — this task is a pure refactor)

**Interfaces:**
- Consumes: `config/byok-providers.json` (Task 1).
- Produces: `_BYOK_BASE_URLS`, `BYOK_ROUTABLE_PROVIDERS`, `BYOK_MODEL_REQUIRED_PROVIDERS` — same names, same values, now catalog-derived. Raises `RuntimeError` at import time if the catalog is missing or malformed.

- [ ] **Step 1: Confirm the existing tests pass before touching anything (baseline)**

Run: `python -m pytest tests/dg/test_llm_auth.py -q`
Expected: all pass (this is your regression baseline — every one of these must still pass after Step 3)

- [ ] **Step 2: Write one new test for the load-once/fail-loud behavior**

Add to `tests/dg/test_llm_auth.py`:

```python
@pytest.mark.unit
class TestByokCatalogLoad:
    """The catalog is loaded once at import time and fails loudly, not silently."""

    def test_missing_catalog_file_raises(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        from digigraph import llm_auth

        monkeypatch.setattr(
            llm_auth, "_BYOK_CATALOG_PATH", tmp_path / "does-not-exist.json"
        )
        with pytest.raises(FileNotFoundError):
            importlib.reload(llm_auth)
        # Restore the real module state for every test that runs after this one.
        importlib.reload(llm_auth)

    def test_malformed_catalog_raises(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        from digigraph import llm_auth

        bad = tmp_path / "byok-providers.json"
        bad.write_text("not json", encoding="utf-8")
        monkeypatch.setattr(llm_auth, "_BYOK_CATALOG_PATH", bad)
        with pytest.raises(ValueError):
            importlib.reload(llm_auth)
        importlib.reload(llm_auth)
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/dg/test_llm_auth.py -k TestByokCatalogLoad -v`
Expected: FAIL — `AttributeError: module 'digigraph.llm_auth' has no attribute '_BYOK_CATALOG_PATH'`

- [ ] **Step 4: Implement the loader**

In `digigraph/src/digigraph/llm_auth.py`, replace the current hardcoded block (lines 33-47):

```python
# BYOK speaks directly to the provider (bypassing the LiteLLM proxy).
_OPENAI_BYOK_BASE_URL = "https://api.openai.com/v1"
_OPENROUTER_BYOK_BASE_URL = "https://openrouter.ai/api/v1"
_GEMINI_BYOK_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_ANTHROPIC_BYOK_BASE_URL = "https://api.anthropic.com/v1/"

# The one table: a provider here is routed to its own endpoint with the user's key.
_BYOK_BASE_URLS: dict[str, str] = {
    "openai": _OPENAI_BYOK_BASE_URL,
    "openrouter": _OPENROUTER_BYOK_BASE_URL,
    "gemini": _GEMINI_BYOK_BASE_URL,
    "anthropic": _ANTHROPIC_BYOK_BASE_URL,
}
BYOK_ROUTABLE_PROVIDERS = tuple(_BYOK_BASE_URLS)
# Providers that require X-BYOK-Model (OpenAI may use the mode default).
BYOK_MODEL_REQUIRED_PROVIDERS = frozenset({"openrouter", "gemini", "anthropic"})
```

with:

```python
import json
from pathlib import Path

# Single source of truth for the BYOK provider allowlist — see
# docs/superpowers/specs/2026-08-13-digichat-byok-model-catalog-design.md.
# Loaded ONCE at import time (not the mtime-recheck-per-call pattern
# model_config.py uses for model_modes.yaml — this changes at the pace of a
# code review, not a redeploy). A missing or malformed catalog raises here,
# crashing the process at startup — loud and immediate in deploy health
# checks, rather than a running process that silently 400s every BYOK
# request. See the design spec's Error handling section for why this
# deliberately differs from model_config.py's own reload behavior.
_BYOK_CATALOG_PATH = Path(__file__).resolve().parents[3] / "config" / "byok-providers.json"


def _load_byok_catalog(path: Path) -> tuple[dict[str, str], frozenset[str]]:
    if not path.exists():
        raise FileNotFoundError(f"BYOK provider catalog not found at {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"BYOK provider catalog at {path} is not valid JSON: {e}") from e
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"BYOK provider catalog at {path} must be a non-empty JSON array")
    base_urls: dict[str, str] = {}
    model_required: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict) or "id" not in entry or "baseUrl" not in entry:
            raise ValueError(f"BYOK provider catalog entry missing id/baseUrl: {entry!r}")
        provider_id = str(entry["id"]).strip().lower()
        base_urls[provider_id] = str(entry["baseUrl"])
        if bool(entry.get("requiresModel")):
            model_required.add(provider_id)
    return base_urls, frozenset(model_required)


_BYOK_BASE_URLS, BYOK_MODEL_REQUIRED_PROVIDERS = _load_byok_catalog(_BYOK_CATALOG_PATH)
BYOK_ROUTABLE_PROVIDERS = tuple(_BYOK_BASE_URLS)
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `python -m pytest tests/dg/test_llm_auth.py -k TestByokCatalogLoad -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Run the FULL baseline suite to confirm zero behavior change**

Run: `python -m pytest tests/dg/test_llm_auth.py -q`
Expected: every test from Step 1 still passes, unchanged — `test_routed_providers_are_supported`, `test_unrouted_providers_are_refused` (still parametrized `["xai", "", "nonsense"]` — xai is not yet in the catalog), `test_every_routable_provider_has_a_base_url`, and every `TestByokGuardOverHttp` test.

- [ ] **Step 7: Run the wider digigraph suite (this module is imported broadly)**

Run: `python -m pytest tests/dg -q`
Expected: all pass

- [ ] **Step 8: Lint**

Run: `ruff check digigraph/src && ruff format --check digigraph/src`

- [ ] **Step 9: Commit**

```bash
git add digigraph/src/digigraph/llm_auth.py tests/dg/test_llm_auth.py
git commit -m "refactor(digigraph): llm_auth loads the BYOK catalog from config/byok-providers.json

Pure refactor — same 4 providers, same base URLs, same model-required set.
Fails loudly (raises at import) on a missing/malformed catalog instead of
degrading to an empty allowlist under live traffic."
```

---

### Task 3: Frontend — `ByokModelOption` type + `use-byok-key.catalog-parity.test.ts`

**Files:**
- Modify: `frontend/digichat/src/hooks/use-byok-key.ts` (add type only, no behavior change)
- Create: `frontend/digichat/src/hooks/use-byok-key.catalog-parity.test.ts`

**Interfaces:**
- Consumes: `config/byok-providers.json` (Task 1).
- Produces: `ByokModelOption` type — consumed by Task 8 (tier bucketing) and Task 11 (UI).

- [ ] **Step 1: Write the failing cross-check test**

```ts
// frontend/digichat/src/hooks/use-byok-key.catalog-parity.test.ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { BYOK_PROVIDER_LIST, byokRequiresModel, type BYOKProvider } from "./use-byok-key";

type CatalogEntry = { id: string; requiresModel?: boolean };

function loadCatalog(): CatalogEntry[] {
  const path = resolve(__dirname, "../../../../../config/byok-providers.json");
  return JSON.parse(readFileSync(path, "utf-8")) as CatalogEntry[];
}

describe("use-byok-key <-> config/byok-providers.json parity", () => {
  it("BYOK_PROVIDER_LIST contains exactly the catalog's provider ids", () => {
    const catalog = loadCatalog();
    const catalogIds = new Set(catalog.map((e) => e.id));
    const tsIds = new Set(BYOK_PROVIDER_LIST as readonly string[]);
    expect(tsIds).toEqual(catalogIds);
  });

  it("byokRequiresModel agrees with the catalog's requiresModel per provider", () => {
    const catalog = loadCatalog();
    for (const entry of catalog) {
      expect(byokRequiresModel(entry.id as BYOKProvider)).toBe(Boolean(entry.requiresModel));
    }
  });
});
```

- [ ] **Step 2: Run to verify it passes immediately (catalog and TS already agree — this test's job is to catch FUTURE drift)**

Run: `cd frontend/digichat && npx vitest run src/hooks/use-byok-key.catalog-parity.test.ts`
Expected: PASS (2 passed) — if this fails right now, stop: Task 1's JSON and today's `use-byok-key.ts` disagree, and that must be resolved before continuing (it would mean the "zero behavior change" premise of Task 1/2 was wrong).

- [ ] **Step 3: Add the `ByokModelOption` type**

In `frontend/digichat/src/hooks/use-byok-key.ts`, add right after the existing `BYOKKeyState` type (currently lines 75-80):

```ts
/** A single model entry once live catalog data exists (Task 8+). Falls back to a
 * flat string per fallbackModels entry with tier undefined when live fetch hasn't
 * run or failed — the picker never blocks on the network. */
export type ByokModelOption = {
  id: string;
  label: string;
  tier?: "free" | "opensource" | "flagship";
  supportsTools?: boolean;
};
```

- [ ] **Step 4: Run the full use-byok-key test file to confirm no regression**

Run: `npx vitest run src/hooks/use-byok-key.test.ts src/hooks/use-byok-key.catalog-parity.test.ts`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/hooks/use-byok-key.ts frontend/digichat/src/hooks/use-byok-key.catalog-parity.test.ts
git commit -m "test(digichat): cross-check use-byok-key against config/byok-providers.json

Same pattern languages.ts documents for its own frontend/backend list —
CI fails the moment one side is edited without the other."
```

---

### Task 4: Add x.ai end-to-end (5th BYOK provider)

**Files:**
- Modify: `config/byok-providers.json` (append entry)
- Modify: `frontend/digichat/src/hooks/use-byok-key.ts` (`BYOKProvider` union, `BYOK_PROVIDER_LIST`, every exhaustive switch)
- Modify: `frontend/digichat/src/components/byok-cli-flow.tsx:380-388` (key placeholder ternary)
- Modify: `frontend/digichat/src/app/api/byok/test/route.ts` (`BYOKProvider` type, `readProvider`, `testKey` switch, new `testXaiKey`)
- Modify: `frontend/digichat/src/app/api/chat/route.ts` (`byokNeedsModel` OR-chain)
- Modify: `tests/dg/test_llm_auth.py` (the 4 parametrize lists that currently treat `"xai"` as unrouted)
- Test: `frontend/digichat/src/hooks/use-byok-key.test.ts`, `frontend/digichat/src/app/api/byok/test/route.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `"xai"` as a full member of `BYOKProvider` and the catalog — flows through every layer this task touches.

- [ ] **Step 1: Add the catalog entry**

In `config/byok-providers.json`, append after the `gemini` entry:

```json
  {
    "id": "xai",
    "label": "x.ai (Grok)",
    "keyPrefix": "xai-",
    "baseUrl": "https://api.x.ai/v1",
    "requiresModel": true,
    "fallbackModels": ["grok-4-3", "grok-4.5"]
  }
```

(Verify `xai-` is x.ai's actual current key prefix against their docs before merging — this repo has no internet access to confirm it from a sandbox; the design spec flags this exact caveat.)

- [ ] **Step 2: Run the parity test — it now fails on purpose, proving it catches drift**

Run: `cd frontend/digichat && npx vitest run src/hooks/use-byok-key.catalog-parity.test.ts`
Expected: FAIL — `BYOK_PROVIDER_LIST` (4 entries) no longer equals the catalog's ids (5 entries). This is the parity test doing its job; proceed to make the TS side agree.

- [ ] **Step 3: Add `"xai"` to `use-byok-key.ts` — TypeScript's exhaustiveness checks will force every switch**

In `frontend/digichat/src/hooks/use-byok-key.ts`:

```ts
export type BYOKProvider = "openai" | "anthropic" | "openrouter" | "gemini" | "xai";

export const BYOK_PROVIDER_LIST: readonly BYOKProvider[] = [
  "openrouter",
  "openai",
  "anthropic",
  "gemini",
  "xai",
];
```

```ts
export function byokRequiresModel(provider: BYOKProvider): boolean {
  return provider !== "openai";
}
```

(No change needed here — `xai !== "openai"` is already `true`, matching the catalog's `requiresModel: true`.)

```ts
export function byokModelPlaceholder(provider: BYOKProvider): string {
  switch (provider) {
    case "openrouter":
      return "openai/gpt-4o-mini";
    case "anthropic":
      return "claude-sonnet-4-20250514";
    case "gemini":
      return "gemini/gemini-2.0-flash";
    case "xai":
      return "grok-4-3";
    case "openai":
      return "gpt-4o-mini";
    default: {
      const _exhaustive: never = provider;
      return _exhaustive;
    }
  }
}
```

```ts
export function byokModelPresets(provider: BYOKProvider): readonly string[] {
  switch (provider) {
    case "openrouter":
      return [
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "anthropic/claude-sonnet-4",
        "google/gemini-2.0-flash",
      ];
    case "openai":
      return ["gpt-4o-mini", "gpt-4o", "o4-mini"];
    case "anthropic":
      return [
        "claude-sonnet-4-20250514",
        "claude-haiku-4-20250514",
        "claude-opus-4-20250514",
      ];
    case "gemini":
      return [
        "gemini/gemini-2.0-flash",
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-pro",
      ];
    case "xai":
      return ["grok-4-3", "grok-4.5"];
    default: {
      const _exhaustive: never = provider;
      return _exhaustive;
    }
  }
}
```

```ts
export function validateBYOKKey(key: string, provider: BYOKProvider): string | null {
  if (!key.trim()) return "API key is required.";
  if (provider === "openai" && !key.startsWith("sk-")) {
    return "OpenAI keys must start with sk-.";
  }
  if (provider === "anthropic" && !key.startsWith("sk-ant-")) {
    return "Anthropic keys must start with sk-ant-.";
  }
  if (provider === "openrouter" && !isOpenRouterKey(key)) {
    return "OpenRouter keys must start with sk-or-.";
  }
  if (provider === "gemini" && !key.startsWith("AI")) {
    return "Gemini keys must start with AI.";
  }
  if (provider === "xai" && !key.startsWith("xai-")) {
    return "x.ai keys must start with xai-.";
  }
  return null;
}
```

- [ ] **Step 4: Fix the key-input placeholder ternary in `byok-cli-flow.tsx`**

In `frontend/digichat/src/components/byok-cli-flow.tsx`, change (currently lines 380-388):

```tsx
                placeholder={
                  provider === "openai"
                    ? "sk-…"
                    : provider === "anthropic"
                      ? "sk-ant-…"
                      : provider === "gemini"
                        ? "AIza…"
                        : provider === "xai"
                          ? "xai-…"
                          : "sk-or-v1-…"
                }
```

- [ ] **Step 5: Run the frontend unit tests to confirm the parity test passes and the exhaustiveness switches compile**

Run: `npx vitest run src/hooks/use-byok-key.test.ts src/hooks/use-byok-key.catalog-parity.test.ts`
Expected: PASS

Run: `npm run build` (Next.js typecheck — this is what actually proves every `switch`'s `never`-exhaustiveness guard was updated; a missed case is a compile error, not a test failure)
Expected: builds cleanly

- [ ] **Step 6: Add x.ai to the BYOK ping route**

In `frontend/digichat/src/app/api/byok/test/route.ts`:

```ts
type BYOKProvider = "openai" | "anthropic" | "openrouter" | "gemini" | "xai";

function readProvider(raw: string): BYOKProvider {
  if (raw === "anthropic") return "anthropic";
  if (raw === "openrouter") return "openrouter";
  if (raw === "gemini") return "gemini";
  if (raw === "xai") return "xai";
  return "openai";
}
```

Add the format check beside the existing ones:

```ts
  if (provider === "xai" && !byokKey.startsWith("xai-")) {
    return jsonResponse({ ok: false, error: "x.ai keys must start with xai-." }, 400);
  }
```

Add `"xai"` to `needsModel`:

```ts
  const needsModel =
    provider === "openrouter" || provider === "anthropic" || provider === "gemini" || provider === "xai";
```

Add the case to `testKey`'s switch:

```ts
async function testKey(
  key: string,
  provider: BYOKProvider,
  model: string
): Promise<TestResult> {
  switch (provider) {
    case "openai":
      return testOpenAIKey(key);
    case "anthropic":
      return testAnthropicKey(key);
    case "openrouter":
      return testOpenRouterKey(key, model);
    case "gemini":
      return testGeminiKey(key);
    case "xai":
      return testXaiKey(key);
    default: {
      const _exhaustive: never = provider;
      return _exhaustive;
    }
  }
}
```

Add the new probe function, mirroring `testOpenAIKey`'s shape (x.ai's API is OpenAI-compatible, so `/v1/models` applies the same way):

```ts
async function testXaiKey(key: string): Promise<TestResult> {
  try {
    const resp = await fetchWithTimeout("https://api.x.ai/v1/models", {
      headers: { Authorization: `Bearer ${key}` },
    });
    if (!resp.ok) {
      const body = (await resp.json().catch(() => ({}))) as {
        error?: { message?: string };
      };
      return { ok: false, error: body.error?.message ?? `x.ai returned HTTP ${resp.status}` };
    }
    const data = (await resp.json()) as { data?: { id: string }[] };
    return { ok: true, model: data.data?.[0]?.id ?? "grok-4-3" };
  } catch (e) {
    return { ok: false, error: abortOrMessage(e) };
  }
}
```

- [ ] **Step 7: Add a test for the new provider**

Add to `frontend/digichat/src/app/api/byok/test/route.test.ts`, after the existing Gemini tests:

```ts
  it("returns 400 for invalid x.ai key prefix", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: {
          "x-byok-key": "not-xai",
          "x-byok-provider": "xai",
          "x-byok-model": "grok-4-3",
        },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("xai-");
  });

  it("returns 400 when x.ai model header missing", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: {
          "x-byok-key": "xai-test",
          "x-byok-provider": "xai",
        },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("Model is required");
  });
```

- [ ] **Step 8: Add x.ai to `chat/route.ts`'s `byokNeedsModel`**

In `frontend/digichat/src/app/api/chat/route.ts` (currently lines 203-206):

```ts
  const byokNeedsModel =
    byokProvider === "openrouter" ||
    byokProvider === "anthropic" ||
    byokProvider === "gemini" ||
    byokProvider === "xai";
```

- [ ] **Step 9: Run the full frontend test suite**

Run: `npm run test`
Expected: all pass (57+ files)

- [ ] **Step 10: Update `test_llm_auth.py` — x.ai is now routable**

In `tests/dg/test_llm_auth.py`, change the parametrize lists (currently lines 208, 213, 249, 262, 270-277):

```python
    @pytest.mark.parametrize("provider", ["openai", "openrouter", "gemini", "anthropic", "xai"])
    def test_routed_providers_are_supported(self, provider: str) -> None:
        assert byok_provider_supported(provider)
        assert provider in BYOK_ROUTABLE_PROVIDERS

    @pytest.mark.parametrize("provider", ["", "nonsense"])
    def test_unrouted_providers_are_refused(self, provider: str) -> None:
        """Each of these would otherwise have been billed to the operator."""
        assert not byok_provider_supported(provider)
```

```python
    @pytest.mark.parametrize("provider", ["nonsense"])
    def test_an_unroutable_key_is_refused_not_silently_swallowed(self, provider: str) -> None:
        res = self._client().get(
            "/healthz", headers={"x-byok-key": "sk-secret", "x-byok-provider": provider}
        )
        assert res.status_code == 400, res.text
        body = res.json()
        assert "byok_provider_unsupported" in str(body)
        assert "openai" in str(body) and "openrouter" in str(body)
        assert "sk-secret" not in res.text

    @pytest.mark.parametrize("provider", ["gemini", "anthropic", "openrouter", "xai"])
    def test_model_required_for_non_openai(self, provider: str) -> None:
        res = self._client().get(
            "/healthz", headers={"x-byok-key": "sk-ok", "x-byok-provider": provider}
        )
        assert res.status_code == 400, res.text
        assert "byok_model_required" in str(res.json())

    @pytest.mark.parametrize(
        "provider,model",
        [
            ("openai", ""),
            ("openrouter", "openai/gpt-4o-mini"),
            ("gemini", "gemini-2.5-flash"),
            ("anthropic", "claude-sonnet-4-6"),
            ("xai", "grok-4-3"),
        ],
    )
    def test_a_routable_key_passes_through(self, provider: str, model: str) -> None:
        headers = {"x-byok-key": "sk-ok", "x-byok-provider": provider}
        if model:
            headers["x-byok-model"] = model
        res = self._client().get("/healthz", headers=headers)
        assert res.status_code == 200, res.text
```

- [ ] **Step 11: Run the digigraph test suite**

Run: `python -m pytest tests/dg/test_llm_auth.py -q`
Expected: all pass

- [ ] **Step 12: Lint both sides**

Run: `npm run lint && ruff check digigraph/src`

- [ ] **Step 13: Commit**

```bash
git add config/byok-providers.json \
  frontend/digichat/src/hooks/use-byok-key.ts \
  frontend/digichat/src/components/byok-cli-flow.tsx \
  frontend/digichat/src/app/api/byok/test/route.ts \
  frontend/digichat/src/app/api/byok/test/route.test.ts \
  frontend/digichat/src/app/api/chat/route.ts \
  tests/dg/test_llm_auth.py
git commit -m "feat: add x.ai as a 5th BYOK provider end-to-end

Frontend picker, ping route, digigraph allowlist — proves the new
single-source-of-truth catalog mechanism with a real 5th provider,
not just a design. Fixed HTTPS base URL, already server-key-registered
in digillm._EXTERNAL_PROVIDERS — none of the SSRF/custom-provider risk
that keeps Ollama/generic-custom-URL out of scope."
```

---

### Task 5: Extract `fetchWithTimeout`/`abortOrMessage` into a shared lib module

**Files:**
- Create: `frontend/digichat/src/lib/fetch-with-timeout.ts`
- Create: `frontend/digichat/src/lib/fetch-with-timeout.test.ts`
- Modify: `frontend/digichat/src/app/api/byok/test/route.ts` (import instead of local copies — behavior-preserving)

**Interfaces:**
- Consumes: nothing.
- Produces: `fetchWithTimeout(url, init, timeoutMs?)`, `abortOrMessage(e, timeoutMs?)`, `DEFAULT_FETCH_TIMEOUT_MS` — consumed by Task 9 (new `/api/byok/models` route) so it doesn't duplicate this logic a second time.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/digichat/src/lib/fetch-with-timeout.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { abortOrMessage, DEFAULT_FETCH_TIMEOUT_MS, fetchWithTimeout } from "./fetch-with-timeout";

describe("fetchWithTimeout", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("resolves normally when fetch resolves before the timeout", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("ok", { status: 200 }));
    const resp = await fetchWithTimeout("https://example.invalid", {});
    expect(resp.status).toBe(200);
  });

  it("aborts and rejects with AbortError when fetch hangs past the timeout", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          const signal = (init as RequestInit)?.signal;
          signal?.addEventListener("abort", () => {
            const err = new Error("The operation was aborted.");
            err.name = "AbortError";
            reject(err);
          });
        }),
    );
    await expect(fetchWithTimeout("https://example.invalid", {}, 5)).rejects.toThrow();
  });
});

describe("abortOrMessage", () => {
  it("formats an AbortError as a timeout message", () => {
    const err = new Error("aborted");
    err.name = "AbortError";
    expect(abortOrMessage(err, DEFAULT_FETCH_TIMEOUT_MS)).toContain("timed out");
  });

  it("passes through a plain Error's message", () => {
    expect(abortOrMessage(new Error("network down"))).toBe("network down");
  });

  it("falls back to a generic message for a non-Error throw", () => {
    expect(abortOrMessage("not an error")).toBe("Unknown error");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/fetch-with-timeout.test.ts`
Expected: FAIL — `Error: Cannot find module './fetch-with-timeout'`

- [ ] **Step 3: Implement**

```ts
// frontend/digichat/src/lib/fetch-with-timeout.ts

/** Shared AbortController-based fetch timeout. Extracted from
 * app/api/byok/test/route.ts so app/api/byok/models/route.ts doesn't
 * duplicate it — see docs/superpowers/specs/2026-08-13-digichat-byok-model-catalog-design.md.
 */

export const DEFAULT_FETCH_TIMEOUT_MS = 10_000;

export async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number = DEFAULT_FETCH_TIMEOUT_MS,
): Promise<globalThis.Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

export function abortOrMessage(e: unknown, timeoutMs: number = DEFAULT_FETCH_TIMEOUT_MS): string {
  if (e instanceof Error) {
    return e.name === "AbortError" ? `Request timed out after ${timeoutMs / 1000} s.` : e.message;
  }
  return "Unknown error";
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/lib/fetch-with-timeout.test.ts`
Expected: PASS (5 passed)

- [ ] **Step 5: Update `byok/test/route.ts` to use the shared module**

In `frontend/digichat/src/app/api/byok/test/route.ts`, delete the local `TIMEOUT_MS` constant, `fetchWithTimeout` function, and `abortOrMessage` function (their current bodies), and add an import:

```ts
import { fetchWithTimeout, abortOrMessage } from "@/lib/fetch-with-timeout";
```

Every existing call site (`testOpenAIKey`, `testAnthropicKey`, `testOpenRouterKey`, `testGeminiKey`, and Task 4's `testXaiKey`) already calls `fetchWithTimeout(url, init)` and `abortOrMessage(e)` with no third argument, so they pick up the shared module's `DEFAULT_FETCH_TIMEOUT_MS = 10_000` automatically — identical behavior to today's local `TIMEOUT_MS = 10_000`.

- [ ] **Step 6: Run the byok/test route tests to confirm zero behavior change**

Run: `npx vitest run src/app/api/byok/test/route.test.ts`
Expected: all pass, unchanged

- [ ] **Step 7: Run the full suite**

Run: `npm run test`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add frontend/digichat/src/lib/fetch-with-timeout.ts \
  frontend/digichat/src/lib/fetch-with-timeout.test.ts \
  frontend/digichat/src/app/api/byok/test/route.ts
git commit -m "refactor(digichat): extract fetchWithTimeout/abortOrMessage to lib/

Second consumer arrives in the next task (app/api/byok/models/route.ts) —
extracting now avoids a second hand-copy of the same 15 lines."
```

---

### Task 6: `byok/test/route.ts` — return the full model list for OpenAI/Anthropic/Gemini

**Files:**
- Modify: `frontend/digichat/src/app/api/byok/test/route.ts`
- Test: `frontend/digichat/src/app/api/byok/test/route.test.ts`

**Interfaces:**
- Consumes: nothing new (same upstream calls this route already makes).
- Produces: `TestResult.models?: { id: string; label: string }[]` — consumed by Task 11 (the picker renders this when present).

- [ ] **Step 1: Write the failing tests**

Add to `frontend/digichat/src/app/api/byok/test/route.test.ts`:

```ts
  it("returns the full model list for a valid OpenAI key, not just the first id", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: [{ id: "gpt-4o-mini" }, { id: "gpt-4o" }, { id: "o4-mini" }] }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/byok/test", {
          method: "POST",
          headers: { "x-byok-key": "sk-test", "x-byok-provider": "openai" },
        }),
      );
      const body = await res.json();
      expect(body.models).toEqual([
        { id: "gpt-4o-mini", label: "gpt-4o-mini" },
        { id: "gpt-4o", label: "gpt-4o" },
        { id: "o4-mini", label: "o4-mini" },
      ]);
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("returns the full model list for a valid Gemini key, from the models[].name shape", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          models: [{ name: "models/gemini-2.0-flash" }, { name: "models/gemini-2.5-flash" }],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/byok/test", {
          method: "POST",
          headers: {
            "x-byok-key": "AIza-test",
            "x-byok-provider": "gemini",
            "x-byok-model": "gemini/gemini-2.0-flash",
          },
        }),
      );
      const body = await res.json();
      expect(body.models).toEqual([
        { id: "gemini-2.0-flash", label: "gemini-2.0-flash" },
        { id: "gemini-2.5-flash", label: "gemini-2.5-flash" },
      ]);
    } finally {
      fetchSpy.mockRestore();
    }
  });
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run src/app/api/byok/test/route.test.ts -t "full model list"`
Expected: FAIL — `body.models` is `undefined`

- [ ] **Step 3: Implement — widen `TestResult` and each probe function**

In `frontend/digichat/src/app/api/byok/test/route.ts`, change the shared type:

```ts
type TestResult = {
  ok: boolean;
  model?: string;
  models?: { id: string; label: string }[];
  error?: string;
};
```

Update `testOpenAIKey` and `testAnthropicKey` (identical shape, `data.data[].id`):

```ts
async function testOpenAIKey(key: string): Promise<TestResult> {
  try {
    const resp = await fetchWithTimeout("https://api.openai.com/v1/models", {
      headers: { Authorization: `Bearer ${key}` },
    });
    if (!resp.ok) {
      const body = (await resp.json().catch(() => ({}))) as {
        error?: { message?: string };
      };
      return { ok: false, error: body.error?.message ?? `OpenAI returned HTTP ${resp.status}` };
    }
    const data = (await resp.json()) as { data?: { id: string }[] };
    const models = (data.data ?? []).map((m) => ({ id: m.id, label: m.id }));
    return { ok: true, model: models[0]?.id ?? "gpt-4o-mini", models };
  } catch (e) {
    return { ok: false, error: abortOrMessage(e) };
  }
}
```

```ts
async function testAnthropicKey(key: string): Promise<TestResult> {
  try {
    const resp = await fetchWithTimeout("https://api.anthropic.com/v1/models", {
      headers: {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
      },
    });
    if (!resp.ok) {
      const body = (await resp.json().catch(() => ({}))) as {
        error?: { message?: string };
      };
      return { ok: false, error: body.error?.message ?? `Anthropic returned HTTP ${resp.status}` };
    }
    const data = (await resp.json()) as { data?: { id: string }[] };
    const models = (data.data ?? []).map((m) => ({ id: m.id, label: m.id }));
    return { ok: true, model: models[0]?.id ?? "claude-3-haiku-20240307", models };
  } catch (e) {
    return { ok: false, error: abortOrMessage(e) };
  }
}
```

Update `testGeminiKey` (different shape — `data.models[].name`, `models/` prefix stripped):

```ts
async function testGeminiKey(key: string): Promise<TestResult> {
  try {
    const resp = await fetchWithTimeout(
      "https://generativelanguage.googleapis.com/v1beta/models",
      { method: "GET", headers: { "x-goog-api-key": key } },
    );
    if (!resp.ok) {
      const body = (await resp.json().catch(() => ({}))) as {
        error?: { message?: string };
      };
      return {
        ok: false,
        error: body.error?.message ?? `Gemini returned HTTP ${resp.status}`,
      };
    }
    const data = (await resp.json()) as { models?: { name?: string }[] };
    const models = (data.models ?? [])
      .map((m) => (m.name ?? "").replace(/^models\//, ""))
      .filter(Boolean)
      .map((id) => ({ id, label: id }));
    return { ok: true, model: models[0]?.id ?? "gemini-2.0-flash", models };
  } catch (e) {
    return { ok: false, error: abortOrMessage(e) };
  }
}
```

- [ ] **Step 4: Run to verify they pass**

Run: `npx vitest run src/app/api/byok/test/route.test.ts`
Expected: all pass, including the two new ones

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/app/api/byok/test/route.ts frontend/digichat/src/app/api/byok/test/route.test.ts
git commit -m "feat(digichat): byok/test route returns full model list, not just first id

Same upstream request each provider already makes — no new network call.
OpenAI/Anthropic share data.data[].id; Gemini is data.models[].name with
the models/ prefix stripped, a genuinely different shape."
```

---

### Task 7: `byok/test/route.ts` — switch OpenRouter validation to `GET /api/v1/key`

**Files:**
- Modify: `frontend/digichat/src/app/api/byok/test/route.ts`
- Test: `frontend/digichat/src/app/api/byok/test/route.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `testOpenRouterKey` no longer requires a `model` argument to validate — the caller no longer needs to pick a model before pinging.

**Verify before implementing:** confirm `GET https://openrouter.ai/api/v1/key`'s exact response shape against OpenRouter's current docs — the design spec flags this as unverified from this sandbox (no internet access). The step below assumes a `{ data: { label, usage, limit, is_free_tier } }`-shaped response (OpenRouter's documented account-info endpoint as of the design spec's writing); adjust the field names in Step 3 if the real response differs.

- [ ] **Step 1: Write the failing tests**

Replace the existing OpenRouter-specific tests in `frontend/digichat/src/app/api/byok/test/route.test.ts` (currently `"returns 400 for invalid OpenRouter key prefix"` and `"returns 400 when OpenRouter model header missing"`) — the second one no longer applies once validation doesn't need a model, so **delete** `"returns 400 when OpenRouter model header missing"` entirely and update the prefix test's mock:

```ts
  it("returns 400 for invalid OpenRouter key prefix", async () => {
    const res = await POST(
      new Request("http://localhost/api/byok/test", {
        method: "POST",
        headers: { "x-byok-key": "sk-proj-bad", "x-byok-provider": "openrouter" },
      })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("sk-or-");
  });

  it("validates an OpenRouter key via GET /api/v1/key with no model required", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: { label: "test-key", limit: 10, usage: 1, is_free_tier: false } }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/byok/test", {
          method: "POST",
          headers: { "x-byok-key": "sk-or-v1-test", "x-byok-provider": "openrouter" },
        }),
      );
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.ok).toBe(true);
      const [url] = fetchSpy.mock.calls[0] as [string];
      expect(url).toBe("https://openrouter.ai/api/v1/key");
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("rejects an OpenRouter key with zero remaining credit even on HTTP 200", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: { label: "exhausted", limit: 10, usage: 10, is_free_tier: false } }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const res = await POST(
        new Request("http://localhost/api/byok/test", {
          method: "POST",
          headers: { "x-byok-key": "sk-or-v1-test", "x-byok-provider": "openrouter" },
        }),
      );
      expect(res.status).toBe(400);
      const body = await res.json();
      expect(body.ok).toBe(false);
      expect(body.error).toContain("credit");
    } finally {
      fetchSpy.mockRestore();
    }
  });
```

Also remove `"openrouter"` from `needsModel` in `route.ts` at this point (Step 3 below), which means the existing model-required test needs no change for `openrouter` specifically since it's being removed from that set — re-run the full file after Step 3 to catch anything else affected.

- [ ] **Step 2: Run to verify the new tests fail**

Run: `npx vitest run src/app/api/byok/test/route.test.ts -t "GET /api/v1/key"`
Expected: FAIL — still hitting the old completions endpoint

- [ ] **Step 3: Implement**

Update `needsModel` (OpenRouter no longer requires a model to validate):

```ts
  const needsModel =
    provider === "anthropic" || provider === "gemini" || provider === "xai";
```

Replace `testOpenRouterKey`:

```ts
async function testOpenRouterKey(key: string): Promise<TestResult> {
  try {
    const resp = await fetchWithTimeout(`${OPENROUTER_API_BASE}/key`, {
      headers: { Authorization: `Bearer ${key}` },
    });
    if (!resp.ok) {
      const body = (await resp.json().catch(() => ({}))) as {
        error?: { message?: string };
      };
      return {
        ok: false,
        error: body.error?.message ?? `OpenRouter returned HTTP ${resp.status}`,
      };
    }
    const data = (await resp.json()) as {
      data?: { limit?: number | null; usage?: number };
    };
    const limit = data.data?.limit;
    const usage = data.data?.usage ?? 0;
    // limit === null means unlimited/no cap on this key — only a finite,
    // fully-consumed limit means "this key has no credit left."
    if (typeof limit === "number" && usage >= limit) {
      return { ok: false, error: "This OpenRouter key has no remaining credit." };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: abortOrMessage(e) };
  }
}
```

Update `testKey`'s dispatch (now single-argument):

```ts
async function testKey(
  key: string,
  provider: BYOKProvider,
  model: string
): Promise<TestResult> {
  switch (provider) {
    case "openai":
      return testOpenAIKey(key);
    case "anthropic":
      return testAnthropicKey(key);
    case "openrouter":
      return testOpenRouterKey(key);
    case "gemini":
      return testGeminiKey(key);
    case "xai":
      return testXaiKey(key);
    default: {
      const _exhaustive: never = provider;
      return _exhaustive;
    }
  }
}
```

(`model` stays an unused parameter on `testKey` for now — the call site still passes it, and `byokNeedsModel`/downstream chat-time validation still requires a model for OpenRouter at the *activation* step, per the design spec's Decisions table: this change only removes the *ping*'s dependency on a chosen model, not the requirement to pick one before activating.)

- [ ] **Step 4: Run to verify tests pass**

Run: `npx vitest run src/app/api/byok/test/route.test.ts`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/app/api/byok/test/route.ts frontend/digichat/src/app/api/byok/test/route.test.ts
git commit -m "feat(digichat): OpenRouter BYOK validation via GET /api/v1/key, not a completion

Cheaper (no completions cost per ping) and no longer needs a model chosen
first. Trade-off named in the design spec: this never exercises OpenRouter's
per-model authorization chain, so a model-restricted key surfaces only on
the first real chat turn — the exhausted-credit case is still caught here
via limit/usage."
```

---

### Task 8: `lib/openrouter-catalog.ts` — pure tier-bucketing function

**Files:**
- Create: `frontend/digichat/src/lib/openrouter-catalog.ts`
- Create: `frontend/digichat/src/lib/openrouter-catalog.test.ts`

**Interfaces:**
- Consumes: `ByokModelOption` (Task 3).
- Produces: `bucketOpenRouterModels(entries) -> { free, opensource, flagship, all }`, `OPENROUTER_CATALOG_ENTRY_CAP` — consumed by Task 9 (the route) and Task 11 (the UI, for tier counts).

No network code here — pure, fully unit-testable logic, per the design spec's price-based (not hand-maintained marker list) tiering decision.

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/digichat/src/lib/openrouter-catalog.test.ts
import { describe, expect, it } from "vitest";
import { bucketOpenRouterModels, OPENROUTER_CATALOG_ENTRY_CAP } from "./openrouter-catalog";

describe("bucketOpenRouterModels", () => {
  it("buckets a $0/$0 model as free", () => {
    const { free, all } = bucketOpenRouterModels([
      { id: "openai/gpt-oss-20b:free", pricing: { prompt: "0", completion: "0" } },
    ]);
    expect(free.map((m) => m.id)).toEqual(["openai/gpt-oss-20b:free"]);
    expect(all).toHaveLength(1);
  });

  it("buckets a model with a hugging_face_id as opensource", () => {
    const { opensource } = bucketOpenRouterModels([
      {
        id: "meta-llama/llama-3.3-70b-instruct",
        pricing: { prompt: "0.0000001", completion: "0.0000003" },
        hugging_face_id: "meta-llama/Llama-3.3-70B-Instruct",
      },
    ]);
    expect(opensource.map((m) => m.id)).toEqual(["meta-llama/llama-3.3-70b-instruct"]);
  });

  it("falls back to the publisher-prefix allowlist when hugging_face_id is absent", () => {
    const { opensource } = bucketOpenRouterModels([
      { id: "qwen/qwen3-coder", pricing: { prompt: "0.0000002", completion: "0.0000006" } },
    ]);
    expect(opensource.map((m) => m.id)).toEqual(["qwen/qwen3-coder"]);
  });

  it("buckets a model priced at/above the flagship floor as flagship", () => {
    const { flagship } = bucketOpenRouterModels([
      // $3 / 1M tokens == 0.000003 / token
      { id: "anthropic/claude-opus-4", pricing: { prompt: "0.000005", completion: "0.000025" } },
    ]);
    expect(flagship.map((m) => m.id)).toEqual(["anthropic/claude-opus-4"]);
  });

  it("a mid-priced, non-open-weight model has no tier but still appears in all", () => {
    const { free, opensource, flagship, all } = bucketOpenRouterModels([
      { id: "some-vendor/mid-tier", pricing: { prompt: "0.0000005", completion: "0.0000015" } },
    ]);
    expect(free).toHaveLength(0);
    expect(opensource).toHaveLength(0);
    expect(flagship).toHaveLength(0);
    expect(all).toHaveLength(1);
    expect(all[0].tier).toBeUndefined();
  });

  it("labels fall back to id when name is absent", () => {
    const { all } = bucketOpenRouterModels([{ id: "vendor/model" }]);
    expect(all[0]).toEqual({ id: "vendor/model", label: "vendor/model", tier: undefined, supportsTools: false });
  });

  it("detects tool support from supported_parameters", () => {
    const { all } = bucketOpenRouterModels([
      { id: "vendor/tool-model", supported_parameters: ["tools", "temperature"] },
    ]);
    expect(all[0].supportsTools).toBe(true);
  });

  it("skips entries with no id", () => {
    const { all } = bucketOpenRouterModels([{ id: "" }, { id: "vendor/ok" }] as never);
    expect(all.map((m) => m.id)).toEqual(["vendor/ok"]);
  });

  it("caps processing at OPENROUTER_CATALOG_ENTRY_CAP entries", () => {
    const entries = Array.from({ length: OPENROUTER_CATALOG_ENTRY_CAP + 500 }, (_, i) => ({
      id: `vendor/model-${i}`,
    }));
    const { all } = bucketOpenRouterModels(entries);
    expect(all).toHaveLength(OPENROUTER_CATALOG_ENTRY_CAP);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/openrouter-catalog.test.ts`
Expected: FAIL — `Cannot find module './openrouter-catalog'`

- [ ] **Step 3: Implement**

```ts
// frontend/digichat/src/lib/openrouter-catalog.ts

/** One entry from OpenRouter's public GET /api/v1/models catalog (fields we use).
 * Exact field names per OpenRouter's documented response shape — re-verify against
 * their live docs before depending on this in production; see the design spec's
 * caveat (this repo has no internet access to confirm it from a sandbox). */
export type OpenRouterCatalogEntry = {
  id: string;
  name?: string;
  pricing?: { prompt?: string; completion?: string };
  hugging_face_id?: string;
  supported_parameters?: string[];
};

export type ByokModelTier = "free" | "opensource" | "flagship";

export type ByokModelOption = {
  id: string;
  label: string;
  tier?: ByokModelTier;
  supportsTools: boolean;
};

/** Entries with no hugging_face_id fall back to this publisher-prefix allowlist for
 * the "opensource" tier — OpenRouter's schema has no universal open-weight signal,
 * unlike price (free/flagship), which is fully data-derived. Explicitly maintained;
 * expect to extend this list over time as new open-weight publishers appear. */
const OPEN_WEIGHT_PUBLISHER_PREFIXES = [
  "meta-llama/",
  "mistralai/",
  "qwen/",
  "deepseek/",
  "google/gemma",
  "thudm/",
  "zai/",
  "moonshotai/",
];

/** $ per 1M input tokens — at/above this, a model buckets as "flagship". Matches the
 * cheapest current frontier tier per docs/LLM_PROVIDERS.md's cheap-paid-API table.
 * A number, not a name list — a new frontier model qualifies the day it's priced,
 * no code change needed (unlike model_config.py's _FLAGSHIP_MODEL_ID_MARKERS). */
const FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M = 3;

export const OPENROUTER_CATALOG_ENTRY_CAP = 2000;

function promptPricePerMillion(entry: OpenRouterCatalogEntry): number | null {
  const raw = entry.pricing?.prompt;
  if (raw === undefined) return null;
  const perToken = Number(raw);
  if (!Number.isFinite(perToken)) return null;
  return perToken * 1_000_000;
}

function isFree(entry: OpenRouterCatalogEntry): boolean {
  return entry.pricing?.prompt === "0" && entry.pricing?.completion === "0";
}

function isOpenSource(entry: OpenRouterCatalogEntry): boolean {
  if (entry.hugging_face_id) return true;
  return OPEN_WEIGHT_PUBLISHER_PREFIXES.some((prefix) => entry.id.startsWith(prefix));
}

function isFlagship(entry: OpenRouterCatalogEntry): boolean {
  const price = promptPricePerMillion(entry);
  return price !== null && price >= FLAGSHIP_PROMPT_PRICE_FLOOR_USD_PER_1M;
}

function tierFor(entry: OpenRouterCatalogEntry): ByokModelTier | undefined {
  if (isFree(entry)) return "free";
  if (isFlagship(entry)) return "flagship";
  if (isOpenSource(entry)) return "opensource";
  return undefined;
}

function supportsTools(entry: OpenRouterCatalogEntry): boolean {
  return Array.isArray(entry.supported_parameters) && entry.supported_parameters.includes("tools");
}

/** Bucket a live OpenRouter catalog into the BYOK picker's tiers. Caps total entries
 * processed — anything beyond the cap is silently dropped, never processed or returned
 * (see the design spec's Security considerations on unbounded response handling). */
export function bucketOpenRouterModels(entries: readonly OpenRouterCatalogEntry[]): {
  free: ByokModelOption[];
  opensource: ByokModelOption[];
  flagship: ByokModelOption[];
  all: ByokModelOption[];
} {
  const capped = entries.slice(0, OPENROUTER_CATALOG_ENTRY_CAP);
  const all: ByokModelOption[] = [];
  const free: ByokModelOption[] = [];
  const opensource: ByokModelOption[] = [];
  const flagship: ByokModelOption[] = [];
  for (const entry of capped) {
    if (!entry.id) continue;
    const option: ByokModelOption = {
      id: entry.id,
      label: entry.name?.trim() || entry.id,
      tier: tierFor(entry),
      supportsTools: supportsTools(entry),
    };
    all.push(option);
    if (option.tier === "free") free.push(option);
    else if (option.tier === "flagship") flagship.push(option);
    else if (option.tier === "opensource") opensource.push(option);
  }
  return { free, opensource, flagship, all };
}
```

- [ ] **Step 4: Run to verify tests pass**

Run: `npx vitest run src/lib/openrouter-catalog.test.ts`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/openrouter-catalog.ts frontend/digichat/src/lib/openrouter-catalog.test.ts
git commit -m "feat(digichat): price-derived OpenRouter tier bucketing (pure function)

Tiers computed from each model's own live pricing/metadata, not a
hand-maintained marker list — the exact staleness problem
docs/LLM_PROVIDERS.md documents for free-tier model ids."
```

---

### Task 9: `app/api/byok/models/route.ts` — the live OpenRouter catalog BFF route

**Files:**
- Create: `frontend/digichat/src/app/api/byok/models/route.ts`
- Create: `frontend/digichat/src/app/api/byok/models/route.test.ts`

**Interfaces:**
- Consumes: `fetchWithTimeout`/`abortOrMessage` (Task 5), `bucketOpenRouterModels` (Task 8), `OPENROUTER_API_BASE` (existing, `lib/byok-openrouter.ts`), `requireDigiChatAuth`, `isEmbedChatRequest`/`resolveEmbedChatTenant`, `checkEmbedIpRateLimit`, `checkBffRateLimit` (all existing).
- Produces: `GET /api/byok/models?provider=openrouter` → `{ ok: true, free, opensource, flagship, all }` — consumed by Task 11 (the UI's prefetch).

This route fixes the real gap the design review caught: `/api/byok/test` has **no rate limit for authenticated/session callers** (only the embed-IP path is limited). This new route applies `checkBffRateLimit` unconditionally, on both paths.

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/digichat/src/app/api/byok/models/route.test.ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";

vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: vi.fn(),
}));
vi.mock("@/lib/embed-chat-tenant", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/embed-chat-tenant")>();
  return { ...actual, resolveEmbedChatTenant: vi.fn(actual.resolveEmbedChatTenant) };
});
vi.mock("@/lib/embed-ip-rate-limit", () => ({
  checkEmbedIpRateLimit: vi.fn(() => ({ allowed: true, retryAfterSec: 0 })),
}));
vi.mock("@/lib/bff-rate-limit", () => ({
  checkBffRateLimit: vi.fn(() => ({ allowed: true })),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";

function req(url: string, headers: Record<string, string> = {}) {
  return new Request(`http://localhost${url}`, { headers });
}

describe("GET /api/byok/models", () => {
  beforeEach(() => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: true });
  });

  it("returns 401 without auth and not an embed request", async () => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    const res = await GET(req("/api/byok/models?provider=openrouter"));
    expect(res.status).toBe(401);
  });

  it("returns 400 for any provider other than openrouter", async () => {
    const res = await GET(req("/api/byok/models?provider=openai"));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBe("unsupported_provider");
  });

  it("rate-limits authenticated callers too, not just embed", async () => {
    vi.mocked(checkBffRateLimit).mockReturnValue({ allowed: false, retryAfterSec: 5 });
    const res = await GET(req("/api/byok/models?provider=openrouter"));
    expect(res.status).toBe(429);
    expect(checkBffRateLimit).toHaveBeenCalled();
  });

  it("fetches OpenRouter's public catalog with no key forwarded and buckets it", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ data: [{ id: "openai/gpt-oss-20b:free", pricing: { prompt: "0", completion: "0" } }] }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      const res = await GET(req("/api/byok/models?provider=openrouter"));
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.ok).toBe(true);
      expect(body.free).toHaveLength(1);
      const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("https://openrouter.ai/api/v1/models");
      expect((init.headers as Record<string, string> | undefined)?.["Authorization"]).toBeUndefined();
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("returns 502 and never throws on a malformed upstream response", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ not_data: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    try {
      const res = await GET(req("/api/byok/models?provider=openrouter"));
      expect(res.status).toBe(502);
      const body = await res.json();
      expect(body.error).toBe("malformed_response");
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("returns 502 on an oversized response without buffering it fully", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", {
        status: 200,
        headers: { "content-type": "application/json", "content-length": String(3_000_000) },
      }),
    );
    try {
      const res = await GET(req("/api/byok/models?provider=openrouter"));
      expect(res.status).toBe(502);
      const body = await res.json();
      expect(body.error).toBe("response_too_large");
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("returns 502 when the upstream request errors/times out", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network down"));
    try {
      const res = await GET(req("/api/byok/models?provider=openrouter"));
      expect(res.status).toBe(502);
    } finally {
      fetchSpy.mockRestore();
    }
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/app/api/byok/models/route.test.ts`
Expected: FAIL — `Error: Cannot find module './route'`

- [ ] **Step 3: Implement**

```ts
// frontend/digichat/src/app/api/byok/models/route.ts
import { requireDigiChatAuth } from "@/lib/request-auth";
import { isEmbedChatRequest, resolveEmbedChatTenant } from "@/lib/embed-chat-tenant";
import { checkEmbedIpRateLimit } from "@/lib/embed-ip-rate-limit";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
import { fetchWithTimeout, abortOrMessage } from "@/lib/fetch-with-timeout";
import { OPENROUTER_API_BASE } from "@/lib/byok-openrouter";
import { bucketOpenRouterModels, type OpenRouterCatalogEntry } from "@/lib/openrouter-catalog";

export const maxDuration = 15;

/** Reject a response body larger than this before fully buffering/parsing it — see
 * the design spec's Error handling section on unbounded response size. */
const MAX_RESPONSE_BYTES = 2_000_000; // 2 MB

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/**
 * GET /api/byok/models — live OpenRouter model catalog for the BYOK picker's tier
 * tabs. OpenRouter's `/models` listing is public (no key needed or forwarded);
 * `provider` is restricted to `openrouter` only — 400 for anything else, so a
 * naive `catalog[provider].baseUrl` mistake can never turn this into an
 * unauthenticated fetch proxy for the other four BYOK providers.
 *
 * Rate-limited on BOTH the embed-IP path AND the authenticated/session path
 * (unlike /api/byok/test, which today only limits the embed-IP path) — this
 * route needs no key at all to trigger, a lower bar than /api/byok/test.
 */
export async function GET(req: Request): Promise<Response> {
  const authResult = await requireDigiChatAuth(req);
  let rateKey: string;
  if (authResult instanceof Response) {
    if (!isEmbedChatRequest(req)) return authResult;
    const embedCtx = resolveEmbedChatTenant(req);
    if (embedCtx instanceof Response) return embedCtx;
    const ipRate = checkEmbedIpRateLimit(req);
    if (!ipRate.allowed) {
      return jsonResponse(
        { error: "rate_limited", message: "Too many requests from this address. Try again shortly." },
        429,
      );
    }
    rateKey = `byok-models:embed:${embedCtx.tenantSlug}`;
  } else {
    rateKey = `byok-models:${authResult.tenantSlug}:${authResult.ownerUserSub}`;
  }

  const rate = checkBffRateLimit(rateKey);
  if (!rate.allowed) {
    return jsonResponse({ error: "rate_limited", message: "Too many requests. Try again shortly." }, 429);
  }

  const provider = (new URL(req.url).searchParams.get("provider") || "").trim().toLowerCase();
  if (provider !== "openrouter") {
    return jsonResponse(
      { error: "unsupported_provider", message: "Only provider=openrouter is supported." },
      400,
    );
  }

  try {
    const resp = await fetchWithTimeout(`${OPENROUTER_API_BASE}/models`, { method: "GET" });
    if (!resp.ok) {
      return jsonResponse({ error: "upstream_error", message: `OpenRouter returned HTTP ${resp.status}` }, 502);
    }
    const contentLength = Number(resp.headers.get("content-length") ?? "0");
    if (contentLength > MAX_RESPONSE_BYTES) {
      return jsonResponse({ error: "response_too_large" }, 502);
    }
    const text = await resp.text();
    if (text.length > MAX_RESPONSE_BYTES) {
      return jsonResponse({ error: "response_too_large" }, 502);
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      return jsonResponse({ error: "malformed_response" }, 502);
    }
    const data = (parsed as { data?: unknown }).data;
    if (!Array.isArray(data)) {
      return jsonResponse({ error: "malformed_response" }, 502);
    }
    const buckets = bucketOpenRouterModels(data as OpenRouterCatalogEntry[]);
    return jsonResponse({ ok: true, ...buckets }, 200);
  } catch (e) {
    return jsonResponse({ ok: false, error: abortOrMessage(e) }, 502);
  }
}
```

- [ ] **Step 4: Run to verify tests pass**

Run: `npx vitest run src/app/api/byok/models/route.test.ts`
Expected: PASS (7 passed)

- [ ] **Step 5: Run the full frontend suite**

Run: `npm run test`
Expected: all pass

- [ ] **Step 6: Lint and build**

Run: `npm run lint && npm run build`

- [ ] **Step 7: Commit**

```bash
git add frontend/digichat/src/app/api/byok/models/route.ts frontend/digichat/src/app/api/byok/models/route.test.ts
git commit -m "feat(digichat): GET /api/byok/models — live OpenRouter catalog for BYOK picker

Same auth gate as /api/byok/test, PLUS a rate limit on the authenticated
path too (a real gap /api/byok/test still has — this route has a lower
trigger bar since it needs no key at all). provider=openrouter only,
size-bounded, malformed-response falls back rather than throwing."
```

---

### Task 10: Non-secret provider/model selection persistence (cookie)

**Files:**
- Modify: `frontend/digichat/src/hooks/use-byok-key.ts`
- Test: `frontend/digichat/src/hooks/use-byok-key.test.ts`

**Interfaces:**
- Consumes: `BYOK_PROVIDER_LIST` (existing).
- Produces: `readByokPrefCookie()`, `writeByokPrefCookie(provider, model)` — consumed by `useBYOKKey()`'s own initial state and `setKey`.

Client-side, non-`httpOnly` cookie (this is a UI preference, not a secret — the key itself is never written here). No new API route: the existing session-authenticated `/api/ecosystem/config` cookie pattern requires a logged-in session, which the anonymous `/embed` surface (where most BYOK usage happens) never has — a plain `document.cookie` read/write needs no server round-trip and works identically on both surfaces.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/digichat/src/hooks/use-byok-key.test.ts`:

```ts
describe("BYOK provider/model preference cookie (non-secret, client-side)", () => {
  beforeEach(() => {
    document.cookie = "digichat_byok_pref=; max-age=0";
  });

  it("returns null when no cookie is set", () => {
    expect(readByokPrefCookie()).toBeNull();
  });

  it("round-trips a written preference", () => {
    writeByokPrefCookie("anthropic", "claude-sonnet-4-20250514");
    expect(readByokPrefCookie()).toEqual({
      provider: "anthropic",
      model: "claude-sonnet-4-20250514",
    });
  });

  it("rejects a cookie naming an unknown provider (defense against a stale/tampered value)", () => {
    document.cookie = `digichat_byok_pref=${encodeURIComponent(
      JSON.stringify({ p: "not-a-real-provider", m: "x" })
    )}`;
    expect(readByokPrefCookie()).toBeNull();
  });

  it("tolerates a malformed cookie value without throwing", () => {
    document.cookie = "digichat_byok_pref=not-json-at-all";
    expect(readByokPrefCookie()).toBeNull();
  });
});
```

Add the import to this test file's existing import block:

```ts
import { readByokPrefCookie, writeByokPrefCookie } from "@/hooks/use-byok-key";
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/hooks/use-byok-key.test.ts -t "preference cookie"`
Expected: FAIL — `readByokPrefCookie is not exported`

- [ ] **Step 3: Implement**

Add to `frontend/digichat/src/hooks/use-byok-key.ts`:

```ts
const BYOK_PREF_COOKIE = "digichat_byok_pref";
const BYOK_PREF_COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 year — non-secret preference only

/** Non-secret provider+model choice, persisted so a returning visitor's picker opens
 * pre-selected. The key itself is NEVER written here — see useBYOKKey's own doc
 * comment. Plain client-side cookie (not httpOnly): read/write directly from the
 * browser, no server round-trip, works on the anonymous /embed surface exactly
 * like the authenticated app shell. */
export function readByokPrefCookie(): { provider: BYOKProvider; model: string } | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${BYOK_PREF_COOKIE}=`));
  if (!match) return null;
  try {
    const raw = decodeURIComponent(match.slice(BYOK_PREF_COOKIE.length + 1));
    const parsed = JSON.parse(raw) as { p?: string; m?: string };
    if (!parsed.p || !(BYOK_PROVIDER_LIST as readonly string[]).includes(parsed.p)) return null;
    return { provider: parsed.p as BYOKProvider, model: parsed.m ?? "" };
  } catch {
    return null;
  }
}

export function writeByokPrefCookie(provider: BYOKProvider, model: string): void {
  if (typeof document === "undefined") return;
  const value = encodeURIComponent(JSON.stringify({ p: provider, m: model }));
  document.cookie = `${BYOK_PREF_COOKIE}=${value}; path=/; max-age=${BYOK_PREF_COOKIE_MAX_AGE}; SameSite=Lax`;
}
```

Wire it into `useBYOKKey()` — initial state reads the cookie for `provider`/`model` only (never `key`/`isSet`), and `setKey` writes it back on every successful activation:

```ts
export function useBYOKKey() {
  const [state, setState] = useState<BYOKKeyState>(() => {
    purgeDurableByokKeys();
    const pref = readByokPrefCookie();
    return pref
      ? { key: "", provider: pref.provider, model: pref.model, isSet: false }
      : emptyByokState();
  });

  const setKey = useCallback((key: string, provider: BYOKProvider, model = "") => {
    // Defense in depth: never leave durable leftovers if an older build wrote them.
    purgeDurableByokKeys();
    writeByokPrefCookie(provider, model);
    setState({ key, provider, model, isSet: key.length > 0 });
  }, []);

  const clearKey = useCallback(() => setKey("", "openrouter", ""), [setKey]);

  return { ...state, setKey, clearKey };
}
```

(`clearKey`'s call to `setKey("", "openrouter", "")` will overwrite the preference cookie back to `openrouter`/empty — if that's undesired, note it as a follow-up; per the design spec, this plan does not special-case "remove" vs. "reconfigure" for cookie purposes.)

- [ ] **Step 4: Run to verify tests pass**

Run: `npx vitest run src/hooks/use-byok-key.test.ts`
Expected: all pass

- [ ] **Step 5: Run the full suite**

Run: `npm run test`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add frontend/digichat/src/hooks/use-byok-key.ts frontend/digichat/src/hooks/use-byok-key.test.ts
git commit -m "feat(digichat): persist BYOK provider+model choice (not the key) across sessions

Plain client-side cookie, no new route — works identically on the
authenticated app shell and the anonymous /embed surface. The key itself
stays session-memory-only, unchanged."
```

---

### Task 11: `byok-cli-flow.tsx` — tier tabs, custom starred set, OpenRouter prefetch

**Files:**
- Modify: `frontend/digichat/src/components/byok-cli-flow.tsx`

**Interfaces:**
- Consumes: `ByokModelOption` (Task 3), `GET /api/byok/models` (Task 9), `TestResult.models` (Task 6).
- Produces: nothing new downstream — this is the UI terminal.

- [ ] **Step 1: Add imports and new state**

At the top of `frontend/digichat/src/components/byok-cli-flow.tsx`, add:

```tsx
import type { ByokModelOption } from "@/hooks/use-byok-key";
```

Inside `ByokCliFlow`, add beside the existing state declarations (after `const [ping, setPing] = useState<ByokPingResult | null>(null);`):

```tsx
  type LiveBuckets = { free: ByokModelOption[]; opensource: ByokModelOption[]; flagship: ByokModelOption[]; all: ByokModelOption[] };
  const [liveModels, setLiveModels] = useState<LiveBuckets | null>(null);
  const [modelsFetchFailed, setModelsFetchFailed] = useState(false);
  const [tier, setTier] = useState<"free" | "opensource" | "flagship" | "all" | "custom">("all");
  const [customIds, setCustomIds] = useState<Set<string>>(new Set());
```

- [ ] **Step 2: Prefetch OpenRouter's catalog as soon as it's the selected provider**

Add this effect right after the existing `useEffect(() => { aliveRef.current = true; ... }, [])` block:

```tsx
  useEffect(() => {
    if (provider !== "openrouter" || liveModels || modelsFetchFailed) return;
    let cancelled = false;
    fetch("/api/byok/models?provider=openrouter", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: LiveBuckets & { ok: boolean }) => {
        if (cancelled) return;
        setLiveModels({ free: data.free, opensource: data.opensource, flagship: data.flagship, all: data.all });
      })
      .catch(() => {
        if (!cancelled) setModelsFetchFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [provider, liveModels, modelsFetchFailed]);
```

- [ ] **Step 3: Compute tiered model options when live data exists**

Replace the existing `modelOptions`/`modelLabels` computation:

```tsx
  const tieredOptions = provider === "openrouter" && liveModels ? liveModels : null;

  const toggleCustom = useCallback((id: string) => {
    setCustomIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const modelOptions = (() => {
    if (tieredOptions) {
      const list = tier === "custom"
        ? tieredOptions.all.filter((m) => customIds.has(m.id))
        : tieredOptions[tier];
      return [...list.map((m) => m.id), CUSTOM_MODEL];
    }
    const presets = [...byokModelPresets(provider)];
    if (!byokRequiresModel(provider)) {
      return ["", ...presets, CUSTOM_MODEL];
    }
    return [...presets, CUSTOM_MODEL];
  })();

  const modelLabels = modelOptions.map((m) => {
    if (m === "") return "(provider default)";
    if (m === CUSTOM_MODEL) return "custom…";
    if (tieredOptions) {
      return tieredOptions.all.find((o) => o.id === m)?.label ?? m;
    }
    return m;
  });
```

- [ ] **Step 4: Extend `TermOptionList` with an optional star-toggle affordance**

Update the `TermOptionList` function's props and render (module scope, above `ByokCliFlowProps`):

```tsx
function TermOptionList({
  options,
  labels,
  highlighted,
  onHighlight,
  onSelect,
  listLabel,
  onToggleStar,
  isStarred,
}: {
  options: readonly string[];
  labels?: readonly string[];
  highlighted: number;
  onHighlight: (i: number) => void;
  onSelect: (value: string) => void;
  listLabel: string;
  onToggleStar?: (value: string) => void;
  isStarred?: (value: string) => boolean;
}) {
```

(Keep the rest of the function body — `listRef`, `useEffect`s, `onKeyDown` — unchanged.) Update just the `<li>` render:

```tsx
      {options.map((opt, i) => {
        const active = i === highlighted;
        return (
          <li key={opt || "(default)"} role="option" aria-selected={active} data-idx={i}>
            {onToggleStar && opt !== CUSTOM_MODEL ? (
              <button
                type="button"
                className="dc-byok-star"
                aria-label={isStarred?.(opt) ? "remove from custom" : "add to custom"}
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleStar(opt);
                }}
              >
                {isStarred?.(opt) ? "★" : "☆"}
              </button>
            ) : null}
            <button
              type="button"
              className={cn("dc-byok-option", active && "dc-byok-option-active")}
              onMouseEnter={() => onHighlight(i)}
              onClick={() => onSelect(opt)}
            >
              <span className="dc-byok-option-cursor" aria-hidden>
                {active ? "❯" : " "}
              </span>
              <span className="font-mono">{labels?.[i] ?? opt}</span>
            </button>
          </li>
        );
      })}
```

- [ ] **Step 5: Render tier tabs and the fetching-models state in the "model" step**

In the `step === "model"` block, right before the existing `{customModel ? (...) : (<TermOptionList ... />)}`, add:

```tsx
              {tieredOptions ? (
                <div className="dc-byok-tier-tabs" role="tablist" aria-label="Model tier">
                  {(["free", "opensource", "flagship", "all", "custom"] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      role="tab"
                      aria-selected={tier === t}
                      className={cn("dc-byok-tier-tab", tier === t && "dc-byok-tier-tab-active")}
                      onClick={() => {
                        setTier(t);
                        setModelHi(0);
                      }}
                    >
                      {t} ({t === "custom" ? customIds.size : tieredOptions[t].length})
                    </button>
                  ))}
                </div>
              ) : null}
```

And update the `TermOptionList` invocation in that same block to pass the star-toggle props:

```tsx
                <TermOptionList
                  options={modelOptions}
                  labels={modelLabels}
                  highlighted={modelHi}
                  onHighlight={setModelHi}
                  onSelect={selectModel}
                  listLabel="BYOK models"
                  onToggleStar={tieredOptions ? toggleCustom : undefined}
                  isStarred={tieredOptions ? (id) => customIds.has(id) : undefined}
                />
```

Add the transitional "fetching" line — right after the `provider: {provider}` line (the existing `{step !== "provider" ? (...) : null}` block), add a sibling:

```tsx
          {provider === "openrouter" && !liveModels && !modelsFetchFailed ? (
            <TermLine marker="·">
              <span className="font-mono text-[12px]" style={{ color: "var(--text-secondary)" }}>
                fetching live model catalog…
              </span>
            </TermLine>
          ) : null}
```

- [ ] **Step 6: Manual verification in the browser**

Run: `npm run dev` (or reuse an already-running dev server per this repo's `.claude/launch.json`), open the app, type `/key` or open the BYOK settings sheet, select `openrouter` as the provider, paste any `sk-or-v1-…`-shaped string, and confirm:
- A brief "fetching live model catalog…" line appears then is replaced by tier tabs with real counts.
- Clicking a tier tab filters the list below it.
- Clicking a star toggles an entry into "custom"'s count.
- Selecting a model still runs the same validate→activate flow as before.

- [ ] **Step 7: Run the full frontend suite, lint, and build**

Run: `npm run test && npm run lint && npm run build`
Expected: all pass, clean build

- [ ] **Step 8: Commit**

```bash
git add frontend/digichat/src/components/byok-cli-flow.tsx
git commit -m "feat(digichat): tier tabs + custom starred set + OpenRouter prefetch in BYOK picker

Prefetch fires as soon as openrouter is the selected provider (no key
needed for the public catalog listing), so tiers are usually warm by the
time the model step renders. Falls back to the flat preset list on
fetch failure — the flow never hard-blocks on the network."
```

---

### Task 12: `byok-cli-flow.test.tsx` — component test for the full stepper

**Files:**
- Create: `frontend/digichat/src/components/byok-cli-flow.test.tsx`

**Interfaces:**
- Consumes: `ByokCliFlow` (Task 11 and all prior).
- Produces: nothing downstream — this closes the pre-existing test-coverage gap the original investigation found (no component test existed for this file before this plan).

- [ ] **Step 1: Check testing-library availability**

Run: `grep -n "@testing-library/react" frontend/digichat/package.json`
If absent, this repo may test components differently — check an existing `*.render.test.tsx` file (e.g. `frontend/digichat-ui/src/DigiChatSession.render.test.tsx`) for the actual rendering/query utilities already in use in this monorepo, and match that pattern instead of assuming `@testing-library/react` — adjust the imports below accordingly before writing Step 2.

- [ ] **Step 2: Write the test**

```tsx
// frontend/digichat/src/components/byok-cli-flow.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ByokCliFlow } from "./byok-cli-flow";

describe("ByokCliFlow", () => {
  beforeEach(() => {
    document.cookie = "digichat_byok_pref=; max-age=0";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("walks provider -> key -> model -> activate for an OpenAI key", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ ok: true, model: "gpt-4o-mini" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    const onActivate = vi.fn();
    render(<ByokCliFlow onClose={() => {}} onActivate={onActivate} />);

    fireEvent.click(screen.getByText("openai"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "sk-test-1234" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });

    const defaultOption = await screen.findByText("(provider default)");
    fireEvent.click(defaultOption);

    await waitFor(() => expect(onActivate).toHaveBeenCalledWith("sk-test-1234", "openai", ""));
    expect(await screen.findByText(/ok — BYOK active for this session/)).toBeInTheDocument();
  });

  it("shows an inline error and does not activate on an invalid key format", async () => {
    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);
    fireEvent.click(screen.getByText("openai"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "not-a-key" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });
    expect(await screen.findByText(/must start with sk-/)).toBeInTheDocument();
  });

  it("refuses activation when the ping fails, and stays on the model step for retry", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ ok: false, error: "Incorrect API key" }), {
          status: 400,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    const onActivate = vi.fn();
    render(<ByokCliFlow onClose={() => {}} onActivate={onActivate} />);
    fireEvent.click(screen.getByText("openai"));
    const keyInput = screen.getByLabelText("Paste API key, then Enter");
    fireEvent.change(keyInput, { target: { value: "sk-bad" } });
    fireEvent.keyDown(keyInput, { key: "Enter" });
    fireEvent.click(await screen.findByText("(provider default)"));
    expect(await screen.findByText("Incorrect API key")).toBeInTheDocument();
    expect(onActivate).not.toHaveBeenCalled();
    expect(screen.getByText("(provider default)")).toBeInTheDocument(); // still on model step
  });

  it("shows OpenRouter tier tabs once the live catalog fetch resolves", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            ok: true,
            free: [{ id: "openai/gpt-oss-20b:free", label: "gpt-oss-20b:free", supportsTools: false }],
            opensource: [],
            flagship: [],
            all: [{ id: "openai/gpt-oss-20b:free", label: "gpt-oss-20b:free", supportsTools: false }],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);
    // openrouter is the default highlighted provider — no click needed to select it as "active",
    // but the prefetch effect only fires once it's the *selected* provider state, so select it explicitly:
    fireEvent.click(screen.getByText("openrouter"));
    await waitFor(() => expect(screen.getByText(/free \(1\)/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Run to verify it passes**

Run: `cd frontend/digichat && npx vitest run src/components/byok-cli-flow.test.tsx`
Expected: PASS — if any query (`getByText`, `getByLabelText`) doesn't match the actual rendered DOM, read the component's current JSX (Task 11's result) and adjust the query, not the component — these are behavior assertions, not implementation details to bend to fit.

- [ ] **Step 4: Run the full frontend suite**

Run: `npm run test`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/components/byok-cli-flow.test.tsx
git commit -m "test(digichat): component coverage for the BYOK stepper

Closes the gap the original BYOK investigation found — no component/UI
test existed for byok-cli-flow.tsx before this. Covers the full
provider->key->model->activate sequence, the invalid-key inline error,
the ping-failure retry path, and the new OpenRouter tier tabs."
```

---

### Task 13: `ARCHITECTURE.md` updates

**Files:**
- Modify: `frontend/digichat/ARCHITECTURE.md`
- Modify: `digigraph/ARCHITECTURE.md`

- [ ] **Step 1: Update `frontend/digichat/ARCHITECTURE.md`**

Run: `grep -n "BYOK providers listed" frontend/digichat/ARCHITECTURE.md` to find the current prose list of providers, and update it to name all 5 (openai, openrouter, anthropic, gemini, xai) and note the catalog file as the source of truth:

```markdown
BYOK providers: OpenAI, OpenRouter, Anthropic, Gemini, x.ai — the canonical
list is `config/byok-providers.json`; `use-byok-key.ts`'s `BYOK_PROVIDER_LIST`
is a hand-written mirror kept honest by a Vitest cross-check test
(`use-byok-key.catalog-parity.test.ts`), the same pattern `languages.ts`
documents for its own frontend/backend list.
```

- [ ] **Step 2: Update `digigraph/ARCHITECTURE.md`**

Run: `grep -n "_BYOK_BASE_URLS\|BYOK_ROUTABLE_PROVIDERS" digigraph/ARCHITECTURE.md` and update whatever prose documents the hardcoded table to instead point at the catalog file:

```markdown
The BYOK provider allowlist (`llm_auth._BYOK_BASE_URLS` /
`BYOK_ROUTABLE_PROVIDERS` / `BYOK_MODEL_REQUIRED_PROVIDERS`) loads from
`config/byok-providers.json` once at import time — this is now the single
source of truth a new provider is added to, not a hand-edited Python dict.
A missing or malformed catalog raises at import, crashing the process at
startup rather than silently 400ing every BYOK request.
```

- [ ] **Step 3: Verify internal doc links**

Run: `make doc-check`
Expected: `check_doc_links: OK`

- [ ] **Step 4: Commit**

```bash
git add frontend/digichat/ARCHITECTURE.md digigraph/ARCHITECTURE.md
git commit -m "docs: update ARCHITECTURE.md for the byok-providers.json catalog + x.ai"
```

---

## Final verification (run before opening the PR)

```bash
cd frontend/digichat && npm run test && npm run lint && npm run build
cd .. && python -m pytest tests/dg -q
ruff check digigraph/src && ruff format --check digigraph/src
make doc-check
```

All must pass. This plan spans two module branches (`module/digichat`, `module/digigraph`) — split the PR accordingly per the Global Constraints note, and remember `llm_auth.py` changes need explicit human review before merge regardless of `make score`.
