# DigiChat Language Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a top-bar language dropdown to DigiChat's embed surface (digithings.ai/chat, OCC, DataTap) that makes the assistant respond in the visitor's chosen language, working identically on both the digigraph backend and the Foundry/DataTap backend.

**Architecture:** A curated 5-language list lives in parallel TS/Python constant modules. The browser sends the choice as an `X-Digi-Language` header (same transport pattern as `X-BYOK-Key`); `route.ts` reads it once and threads it to whichever backend adapter is active. digigraph declares a new `response_language` field on `WorkflowRequest`/`WorkflowState` and appends a short directive to whichever `system_prompt` `research_node` already resolved. Foundry has no system-prompt slot, so its adapter prepends a bracketed directive to the per-turn `input` text instead.

**Tech Stack:** Next.js 15 / React / TypeScript (Vitest), Python 3.12 / Pydantic v2 / LangGraph (pytest).

## Global Constraints

- Polars/Pydantic v2/ruff-compliant on the Python side; line length 100 (repo-wide, CLAUDE.md).
- `response_language` **must** be declared on `WorkflowState` in the same commit that starts setting it — LangGraph's `StateGraph(WorkflowState)` silently drops undeclared `TypedDict` keys (issue #2097's bug class).
- Never string-interpolate a raw header/body value into a prompt — only the mapped `{code: display_name}` value ever reaches prompt text; unknown codes are silently ignored (no exception, no directive).
- Curated languages, exact codes and display names, used verbatim in every file below:
  | code | display name |
  |---|---|
  | `en` | English |
  | `de` | German |
  | `it` | Italian |
  | `es` | Spanish |
  | `fr` | French |
- Default-on: `showLanguageSelector` is `true` for any real registered tenant unless explicitly set to `false`; the *fallback* gated config (`DEFAULT_EMBED_TENANT_CONFIG`, used when a tenant can't be resolved) stays `false`, matching that config's existing "fail restrictive" rule.
- Session-only client state: no `localStorage`. Seeded once from `navigator.language` on mount; resets to a fresh auto-detect on reload.
- Design reference: `docs/superpowers/specs/2026-08-10-digichat-language-selector-design.md`. Issue: [#2103](https://github.com/digithings-ai/digithings/issues/2103).
- Branching: this feature touches both `digigraph` and `frontend/digichat`. Current repo precedent for cross-cutting work (PR #2101, PR #2099) branches `task/2103-<slug>` directly off **`develop`** rather than either module branch — follow that precedent, not the idealized two-hop split. (`module/digichat` and `module/digigraph` were separately synced with develop this session and remain available for any future single-component task.)

---

## Backend (digigraph)

### Task 1: Language directive module

**Files:**
- Create: `digigraph/src/digigraph/languages.py`
- Test: `tests/dg/test_languages.py`

**Interfaces:**
- Produces: `LANGUAGE_NAMES: dict[str, str]`, `resolve_language_directive(code: str | None) -> str | None` — used by Task 3's `research_node`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/dg/test_languages.py
"""Unit tests for the response-language directive builder."""

from __future__ import annotations

import pytest

from digigraph.languages import LANGUAGE_NAMES, resolve_language_directive

pytestmark = pytest.mark.unit


def test_language_names_covers_the_curated_list() -> None:
    assert LANGUAGE_NAMES == {
        "en": "English",
        "de": "German",
        "it": "Italian",
        "es": "Spanish",
        "fr": "French",
    }


def test_resolve_language_directive_for_known_non_english_code() -> None:
    directive = resolve_language_directive("de")
    assert directive is not None
    assert "German" in directive


def test_resolve_language_directive_is_case_insensitive() -> None:
    assert resolve_language_directive("DE") == resolve_language_directive("de")


def test_resolve_language_directive_none_for_english() -> None:
    assert resolve_language_directive("en") is None


@pytest.mark.parametrize("bad", [None, "", "  ", "xx", "klingon", "<script>"])
def test_resolve_language_directive_none_for_unknown_or_missing(bad: str | None) -> None:
    assert resolve_language_directive(bad) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd digigraph && uv run pytest ../tests/dg/test_languages.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'digigraph.languages'`

- [ ] **Step 3: Write minimal implementation**

```python
# digigraph/src/digigraph/languages.py
"""Curated response-language directive for DigiChat's language selector (#2103).

Only the mapped display name below ever reaches a prompt — the raw
X-Digi-Language header/request value is never interpolated directly, so an
unrecognized or crafted value can at most be ignored, never inject text.
"""

from __future__ import annotations

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "de": "German",
    "it": "Italian",
    "es": "Spanish",
    "fr": "French",
}


def resolve_language_directive(code: str | None) -> str | None:
    """Return a short prompt-append directive for *code*, or None.

    None means "no preference" — covers missing/empty/unrecognized codes and
    the English default (English needs no directive, since prompts are
    already English).
    """
    if not code:
        return None
    normalized = str(code).strip().lower()
    if not normalized or normalized == "en":
        return None
    name = LANGUAGE_NAMES.get(normalized)
    if not name:
        return None
    return (
        f"Respond to the user only in {name}. "
        "Keep this instruction to yourself — do not mention or translate it."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd digigraph && uv run pytest ../tests/dg/test_languages.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add digigraph/src/digigraph/languages.py tests/dg/test_languages.py
git commit -m "feat(digigraph): add response-language directive resolver (#2103)"
```

---

### Task 2: Declare `response_language` on the request and graph state

**Files:**
- Modify: `digigraph/src/digigraph/models.py` (`WorkflowRequest`, after `research_system_prompt_override`)
- Modify: `digigraph/src/digigraph/graph/state.py` (`WorkflowState`)
- Modify: `digigraph/src/digigraph/workflow.py` (`_initial_graph_state`)
- Modify: `digigraph/ARCHITECTURE.md` (state table, next to `research_system_prompt_override`)
- Test: `tests/dg/test_languages.py` (append to the file from Task 1)

**Interfaces:**
- Consumes: nothing new.
- Produces: `WorkflowRequest.response_language: str | None`, `WorkflowState["response_language"]` — consumed by Task 3's `research_node`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/dg/test_languages.py`:

```python
from digigraph.graph.state import WorkflowState
from digigraph.models import WorkflowRequest
from digigraph.workflow import _initial_graph_state


def test_workflow_state_declares_response_language() -> None:
    """LangGraph drops undeclared TypedDict keys — see #2097."""
    assert "response_language" in WorkflowState.__annotations__


def test_initial_graph_state_carries_response_language() -> None:
    state = _initial_graph_state(
        WorkflowRequest(prompt="hi", response_language="de"),
        "wf-lang",
    )
    assert state["response_language"] == "de"


def test_initial_graph_state_omits_response_language_when_unset() -> None:
    state = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-lang-2")
    assert "response_language" not in state


def test_langgraph_preserves_response_language_through_invoke() -> None:
    """Regression: StateGraph(WorkflowState) must not strip response_language."""
    from langgraph.graph import END, START, StateGraph

    seen: dict[str, str | None] = {}

    def _capture(state: WorkflowState) -> dict:
        seen["response_language"] = state.get("response_language")
        return {}

    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    builder.add_node("capture", _capture)
    builder.add_edge(START, "capture")
    builder.add_edge("capture", END)
    graph = builder.compile()
    graph.invoke({"prompt": "x", "response_language": "de"})
    assert seen["response_language"] == "de"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd digigraph && uv run pytest ../tests/dg/test_languages.py -v`
Expected: FAIL — `WorkflowRequest` has no field `response_language` (Pydantic `extra="forbid"` raises on construction), and `"response_language" in WorkflowState.__annotations__` is `False`.

- [ ] **Step 3: Write minimal implementation**

In `digigraph/src/digigraph/models.py`, add immediately after `research_system_prompt_override`:

```python
    response_language: str | None = Field(
        None,
        description=(
            "Per-request response language code (X-Digi-Language). One of the curated "
            "codes in digigraph.languages.LANGUAGE_NAMES; unrecognized values are ignored."
        ),
    )
```

In `digigraph/src/digigraph/graph/state.py`, add next to the existing corpus-routing fields:

```python
    # Per-request response language (X-Digi-Language). Must be declared here — see the
    # digisearch_index/vault_path_prefix comment above; same LangGraph pitfall (#2097).
    response_language: str | None
```

In `digigraph/src/digigraph/workflow.py`, in `_initial_graph_state`, add immediately after the `research_system_prompt_override` block:

```python
    if req.response_language:
        initial["response_language"] = req.response_language
```

In `digigraph/ARCHITECTURE.md`, add a row to the `WorkflowState` fields table next to `research_system_prompt_override`:

```markdown
| `response_language` | `str \| None` | Per-request response-language code (`X-Digi-Language`). **Must** be declared — LangGraph drops undeclared keys. See `digigraph.languages`. |
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd digigraph && uv run pytest ../tests/dg/test_languages.py -v`
Expected: PASS (10 passed)

Then run the full digigraph unit suite to confirm nothing else broke:
Run: `cd digigraph && uv run pytest -m unit -q`
Expected: all passing, same count as before plus the new tests.

- [ ] **Step 5: Commit**

```bash
git add digigraph/src/digigraph/models.py digigraph/src/digigraph/graph/state.py \
        digigraph/src/digigraph/workflow.py digigraph/ARCHITECTURE.md tests/dg/test_languages.py
git commit -m "feat(digigraph): declare response_language on WorkflowRequest/WorkflowState (#2103)"
```

---

### Task 3: Append the language directive in `research_node`

**Files:**
- Modify: `digigraph/src/digigraph/graph/research.py` (`research_node`)
- Test: `tests/dg/test_languages.py` (append)

**Interfaces:**
- Consumes: `resolve_language_directive` from Task 1, `state["response_language"]` from Task 2.
- Produces: nothing further downstream — this is the terminal consumer.

- [ ] **Step 1: Write the failing tests**

Append to `tests/dg/test_languages.py`:

```python
from digigraph.graph.research import research_node


def test_research_node_appends_directive_for_known_language(monkeypatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    captured: dict = {}

    def fake_document_rag_path(*, system_prompt, **_kwargs):
        captured["system_prompt"] = system_prompt
        return {"research_note": "ok"}

    monkeypatch.setattr(
        "digigraph.graph.research._run_document_rag_path",
        lambda **kwargs: fake_document_rag_path(**kwargs),
    )
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )
    research_node({"prompt": "hallo", "response_language": "de"})
    assert "You are a helpful assistant." in captured["system_prompt"]
    assert "German" in captured["system_prompt"]


def test_research_node_leaves_prompt_unchanged_for_english_or_unset(monkeypatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    captured: dict = {}

    monkeypatch.setattr(
        "digigraph.graph.research._run_document_rag_path",
        lambda **kwargs: captured.update(system_prompt=kwargs["system_prompt"]) or {"research_note": "ok"},
    )
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )
    research_node({"prompt": "hi", "response_language": "en"})
    assert captured["system_prompt"] == "You are a helpful assistant."


def test_research_node_appends_directive_to_tenant_override_prompt(monkeypatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    captured: dict = {}

    monkeypatch.setattr(
        "digigraph.graph.research._run_document_rag_path",
        lambda **kwargs: captured.update(system_prompt=kwargs["system_prompt"]) or {"research_note": "ok"},
    )
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "occ_help", "occ_help", "You are a helpful assistant."),
    )
    research_node(
        {
            "prompt": "hallo",
            "response_language": "de",
            "research_system_prompt_override": "You are the OCC help assistant.",
        }
    )
    assert captured["system_prompt"].startswith("You are the OCC help assistant.")
    assert "German" in captured["system_prompt"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd digigraph && uv run pytest ../tests/dg/test_languages.py -v`
Expected: FAIL — the three new tests fail because `system_prompt` has no language directive appended yet (assertions on `"German" in ...` fail).

- [ ] **Step 3: Write minimal implementation**

In `digigraph/src/digigraph/graph/research.py`, in `research_node`, immediately after the existing block:

```python
    override_prompt = state.get("research_system_prompt_override")
    if override_prompt and str(override_prompt).strip():
        system_prompt = str(override_prompt).strip()
```

add:

```python
    language_directive = resolve_language_directive(state.get("response_language"))
    if language_directive:
        system_prompt = f"{system_prompt}\n\n{language_directive}"
```

and add the import near the top of the file, alongside the other `digigraph.*` imports:

```python
from digigraph.languages import resolve_language_directive
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd digigraph && uv run pytest ../tests/dg/test_languages.py -v`
Expected: PASS (13 passed)

Run the full digigraph suite once more:
Run: `cd digigraph && uv run pytest -m unit -q`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add digigraph/src/digigraph/graph/research.py tests/dg/test_languages.py
git commit -m "feat(digigraph): append response-language directive in research_node (#2103)"
```

---

## Frontend (frontend/digichat) — shared language list

### Task 4: Curated language list + browser detection helpers

**Files:**
- Create: `frontend/digichat/src/lib/languages.ts`
- Test: `frontend/digichat/src/lib/languages.test.ts`

**Interfaces:**
- Produces: `LANGUAGES: { code: string; label: string }[]`, `DEFAULT_LANGUAGE_CODE: "en"`, `resolveLanguageCode(input: string | null | undefined): string`, `detectBrowserLanguageCode(): string` — used by Task 6 (dropdown), Task 8 (hook), Task 9 (embed wiring).

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/digichat/src/lib/languages.test.ts
import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_LANGUAGE_CODE,
  LANGUAGES,
  detectBrowserLanguageCode,
  resolveLanguageCode,
} from "@/lib/languages";

describe("LANGUAGES", () => {
  it("is the curated 5-language list", () => {
    expect(LANGUAGES).toEqual([
      { code: "en", label: "English" },
      { code: "de", label: "German" },
      { code: "it", label: "Italian" },
      { code: "es", label: "Spanish" },
      { code: "fr", label: "French" },
    ]);
  });
});

describe("resolveLanguageCode", () => {
  it("passes through a known lowercase code", () => {
    expect(resolveLanguageCode("de")).toBe("de");
  });

  it("lowercases a known code", () => {
    expect(resolveLanguageCode("DE")).toBe("de");
  });

  it.each([null, undefined, "", "  ", "xx", "klingon", "<script>"])(
    "falls back to English for %p",
    (bad) => {
      expect(resolveLanguageCode(bad)).toBe(DEFAULT_LANGUAGE_CODE);
    },
  );
});

describe("detectBrowserLanguageCode", () => {
  it("matches a curated language from navigator.language", () => {
    vi.stubGlobal("navigator", { language: "de-DE" });
    expect(detectBrowserLanguageCode()).toBe("de");
    vi.unstubAllGlobals();
  });

  it("falls back to English for an uncurated browser locale", () => {
    vi.stubGlobal("navigator", { language: "ja-JP" });
    expect(detectBrowserLanguageCode()).toBe("en");
    vi.unstubAllGlobals();
  });

  it("falls back to English when navigator is unavailable", () => {
    vi.stubGlobal("navigator", undefined);
    expect(detectBrowserLanguageCode()).toBe("en");
    vi.unstubAllGlobals();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/languages.test.ts`
Expected: FAIL with "Cannot find module '@/lib/languages'"

- [ ] **Step 3: Write minimal implementation**

```typescript
// frontend/digichat/src/lib/languages.ts
/**
 * Curated response-language list for DigiChat's language selector (#2103).
 * Kept in exact sync with digigraph's `digigraph.languages.LANGUAGE_NAMES` —
 * see `tests/dg/test_languages.py` on the Python side and this file's test
 * for the codes; there is no shared module across the two languages, so any
 * change here must be mirrored there by hand.
 */
export const LANGUAGES: { code: string; label: string }[] = [
  { code: "en", label: "English" },
  { code: "de", label: "German" },
  { code: "it", label: "Italian" },
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
];

export const DEFAULT_LANGUAGE_CODE = "en";

const KNOWN_CODES = new Set(LANGUAGES.map((l) => l.code));

/** Validates/normalizes a language code from user input or a header. Never
 * returns anything outside the curated list — unknown/missing input falls
 * back to English. */
export function resolveLanguageCode(input: string | null | undefined): string {
  const normalized = (input ?? "").trim().toLowerCase();
  return KNOWN_CODES.has(normalized) ? normalized : DEFAULT_LANGUAGE_CODE;
}

/** Best-effort initial guess from the browser's locale; always a curated
 * code, defaulting to English. Safe to call during render (no exceptions on
 * a missing/unusual `navigator`). */
export function detectBrowserLanguageCode(): string {
  if (typeof navigator === "undefined" || !navigator?.language) {
    return DEFAULT_LANGUAGE_CODE;
  }
  const primary = navigator.language.split("-")[0]?.toLowerCase() ?? "";
  return resolveLanguageCode(primary);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/digichat && npx vitest run src/lib/languages.test.ts`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/languages.ts frontend/digichat/src/lib/languages.test.ts
git commit -m "feat(digichat): add curated language list + browser detection (#2103)"
```

---

### Task 5: Tenant config plumbing — `showLanguageSelector`

**Files:**
- Modify: `frontend/digichat/src/lib/embed-tenants.ts` (`EmbedTenantConfig` type + `validateEntry`)
- Modify: `frontend/digichat/src/lib/embed-client-config.ts` (`EmbedTenantClientConfig`, `toEmbedClientConfig`, `DEFAULT_EMBED_TENANT_CONFIG`)
- Modify: `frontend/digichat/src/lib/embed-ui-flags.ts` (`resolveEmbedUiFlags`)
- Modify: `frontend/digichat/src/lib/embed-tenants.test.ts`, `frontend/digichat/src/lib/embed-ui-flags.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `EmbedTenantConfig.showLanguageSelector?: boolean`, `EmbedTenantClientConfig.showLanguageSelector?: boolean` (always concrete by the time it leaves `toEmbedClientConfig`/`DEFAULT_EMBED_TENANT_CONFIG`), `resolveEmbedUiFlags(...).showLanguageSelector: boolean` — consumed by Task 9.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/digichat/src/lib/embed-tenants.test.ts` (mirror the existing `showByok` test cases in that file):

```typescript
it("accepts showLanguageSelector: false", () => {
  const registry = parseEmbedTenants(
    JSON.stringify({
      "example.com": {
        slug: "example",
        gateMode: "ungated",
        token: "t",
        showLanguageSelector: false,
      },
    }),
  );
  expect(registry.get("example.com")?.showLanguageSelector).toBe(false);
});

it("rejects a non-boolean showLanguageSelector", () => {
  expect(() =>
    parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          gateMode: "ungated",
          token: "t",
          showLanguageSelector: "yes",
        },
      }),
    ),
  ).toThrow(/showLanguageSelector must be a boolean/);
});

it("leaves showLanguageSelector undefined when unset", () => {
  const registry = parseEmbedTenants(
    JSON.stringify({
      "example.com": { slug: "example", gateMode: "ungated", token: "t" },
    }),
  );
  expect(registry.get("example.com")?.showLanguageSelector).toBeUndefined();
});
```

Add a new test file section (or append if a `toEmbedClientConfig` test already exists in `embed-tenants.test.ts` — check first; if not, add to `frontend/digichat/src/lib/embed-client-config.test.ts`, creating it if it does not exist):

```typescript
// frontend/digichat/src/lib/embed-client-config.test.ts
import { describe, expect, it } from "vitest";
import {
  DEFAULT_EMBED_TENANT_CONFIG,
  toEmbedClientConfig,
} from "@/lib/embed-client-config";
import type { EmbedTenantConfig } from "@/lib/embed-tenants";

const BASE: EmbedTenantConfig = {
  slug: "example",
  gateMode: "ungated",
  theme: "dark",
  attribution: false,
  activityDetail: "labels",
  token: "t",
  backend: { type: "digigraph" },
};

describe("toEmbedClientConfig — showLanguageSelector", () => {
  it("defaults to true when the registry entry doesn't set it", () => {
    expect(toEmbedClientConfig(BASE).showLanguageSelector).toBe(true);
  });

  it("passes through an explicit false", () => {
    expect(
      toEmbedClientConfig({ ...BASE, showLanguageSelector: false }).showLanguageSelector,
    ).toBe(false);
  });

  it("passes through an explicit true", () => {
    expect(
      toEmbedClientConfig({ ...BASE, showLanguageSelector: true }).showLanguageSelector,
    ).toBe(true);
  });
});

describe("DEFAULT_EMBED_TENANT_CONFIG", () => {
  it("is false — an unresolved/gated tenant never shows it", () => {
    expect(DEFAULT_EMBED_TENANT_CONFIG.showLanguageSelector).toBe(false);
  });
});
```

Append to `frontend/digichat/src/lib/embed-ui-flags.test.ts`:

```typescript
it("resolveEmbedUiFlags passes showLanguageSelector through", () => {
  expect(resolveEmbedUiFlags({ ...BASE_CLIENT_CONFIG, showLanguageSelector: true }).showLanguageSelector).toBe(true);
  expect(resolveEmbedUiFlags({ ...BASE_CLIENT_CONFIG, showLanguageSelector: false }).showLanguageSelector).toBe(false);
});
```

(If `embed-ui-flags.test.ts` has no `BASE_CLIENT_CONFIG` fixture already, use whatever minimal `EmbedTenantClientConfig` object the existing `showByok`/`layout` tests in that file already construct — match that exact fixture rather than inventing a new one.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-tenants.test.ts src/lib/embed-client-config.test.ts src/lib/embed-ui-flags.test.ts`
Expected: FAIL — `showLanguageSelector` is not a recognized field / `toEmbedClientConfig` doesn't return it / module `embed-client-config.test.ts` doesn't exist yet if newly created.

- [ ] **Step 3: Write minimal implementation**

In `frontend/digichat/src/lib/embed-tenants.ts`, add to the `EmbedTenantConfig` type, next to `showByok`:

```typescript
  /**
   * When true (or unset — see toEmbedClientConfig), the embed shows a
   * language dropdown in the header. Independent of gateMode/showByok.
   * Only an explicit `false` here turns it off for this tenant.
   */
  showLanguageSelector?: boolean;
```

In `validateEntry`, next to the `showByok` validation:

```typescript
  if (v.showLanguageSelector !== undefined && typeof v.showLanguageSelector !== "boolean") {
    throw new Error(`${ctx}: showLanguageSelector must be a boolean`);
  }
```

In the same function's return object, next to `showByok`:

```typescript
    showLanguageSelector:
      typeof v.showLanguageSelector === "boolean" ? v.showLanguageSelector : undefined,
```

In `frontend/digichat/src/lib/embed-client-config.ts`, add to `EmbedTenantClientConfig`:

```typescript
  showLanguageSelector?: boolean;
```

In `DEFAULT_EMBED_TENANT_CONFIG`:

```typescript
  showLanguageSelector: false,
```

In `toEmbedClientConfig`, next to `showByok: cfg.showByok ?? false,`:

```typescript
    // Default ON for any real, registered tenant — the opposite default from
    // showByok, by product decision (#2103). DEFAULT_EMBED_TENANT_CONFIG
    // above (the unresolved/gated fallback) stays false.
    showLanguageSelector: cfg.showLanguageSelector ?? true,
```

In `frontend/digichat/src/lib/embed-ui-flags.ts`, extend the return type and object of `resolveEmbedUiFlags`:

```typescript
export function resolveEmbedUiFlags(cfg: EmbedTenantClientConfig): {
  showByok: boolean;
  layout: "page" | "embed";
  showLanguageSelector: boolean;
} {
  return {
    showByok: cfg.showByok === true,
    layout: cfg.layout === "page" ? "page" : "embed",
    showLanguageSelector: cfg.showLanguageSelector === true,
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-tenants.test.ts src/lib/embed-client-config.test.ts src/lib/embed-ui-flags.test.ts`
Expected: PASS (all cases green)

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/embed-tenants.ts frontend/digichat/src/lib/embed-tenants.test.ts \
        frontend/digichat/src/lib/embed-client-config.ts frontend/digichat/src/lib/embed-client-config.test.ts \
        frontend/digichat/src/lib/embed-ui-flags.ts frontend/digichat/src/lib/embed-ui-flags.test.ts
git commit -m "feat(digichat): thread showLanguageSelector through tenant config (#2103)"
```

---

### Task 6: `LanguageSelect` dropdown component

**Files:**
- Create: `frontend/digichat/src/components/language-select.tsx`
- Test: `frontend/digichat/src/components/language-select.test.tsx`

**Interfaces:**
- Consumes: `LANGUAGES` from Task 4.
- Produces: `LanguageSelect({ value, onChange }: { value: string; onChange: (code: string) => void })` — a controlled component, consumed by Task 9.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/digichat/src/components/language-select.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LanguageSelect } from "@/components/language-select";

describe("LanguageSelect", () => {
  it("renders the currently selected language's label as the trigger text", () => {
    render(<LanguageSelect value="de" onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /german/i })).toBeInTheDocument();
  });

  it("lists all five curated languages when opened", async () => {
    const user = userEvent.setup();
    render(<LanguageSelect value="en" onChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: /english/i }));
    for (const label of ["English", "German", "Italian", "Spanish", "French"]) {
      expect(screen.getByRole("menuitem", { name: label })).toBeInTheDocument();
    }
  });

  it("calls onChange with the picked language's code", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<LanguageSelect value="en" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /english/i }));
    await user.click(screen.getByRole("menuitem", { name: "German" }));
    expect(onChange).toHaveBeenCalledWith("de");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/components/language-select.test.tsx`
Expected: FAIL with "Cannot find module '@/components/language-select'"

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/digichat/src/components/language-select.tsx
"use client";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LANGUAGES, resolveLanguageCode } from "@/lib/languages";

export function LanguageSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (code: string) => void;
}) {
  const current = LANGUAGES.find((l) => l.code === resolveLanguageCode(value)) ?? LANGUAGES[0]!;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label={`Response language: ${current.label}`}>
          {current.label}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {LANGUAGES.map((lang) => (
          <DropdownMenuItem key={lang.code} onSelect={() => onChange(lang.code)}>
            {lang.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/digichat && npx vitest run src/components/language-select.test.tsx`
Expected: PASS (3 passed)

If the accessible name query doesn't match (Radix's `DropdownMenuTrigger`/`DropdownMenuItem` role names can differ slightly from a plain `button`/`menuitem`), inspect the rendered output with `screen.debug()` and adjust the queries to match `dropdown-menu.tsx`'s actual rendered roles — do not change the component's behavior to satisfy the test.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/components/language-select.tsx frontend/digichat/src/components/language-select.test.tsx
git commit -m "feat(digichat): add LanguageSelect dropdown component (#2103)"
```

---

### Task 7: `useEmbedDigiChat` sends `X-Digi-Language`

**Files:**
- Modify: `frontend/digichat/src/hooks/use-embed-digi-chat.ts`
- Modify: `frontend/digichat/src/hooks/use-embed-digi-chat.test.ts`

**Interfaces:**
- Consumes: `resolveLanguageCode`, `DEFAULT_LANGUAGE_CODE` from Task 4.
- Produces: `UseEmbedDigiChatOptions.responseLanguage?: string` — consumed by Task 9.

- [ ] **Step 1: Write the failing test**

Read `frontend/digichat/src/hooks/use-embed-digi-chat.test.ts` first to match its existing test harness for asserting on `prepareSendMessagesRequest`-produced headers (it already has cases for `X-BYOK-Key` — follow that exact pattern for the transport mock/assertion style). Add:

```typescript
it("sets X-Digi-Language when responseLanguage is a non-English curated code", async () => {
  const { headers } = await callPrepareSendMessagesRequest({
    // ...same base options the X-BYOK-Key test uses...
    responseLanguage: "de",
  });
  expect(headers.get("X-Digi-Language")).toBe("de");
});

it("omits X-Digi-Language when responseLanguage is English or unset", async () => {
  const { headers: withEnglish } = await callPrepareSendMessagesRequest({
    responseLanguage: "en",
  });
  expect(withEnglish.has("X-Digi-Language")).toBe(false);

  const { headers: withUnset } = await callPrepareSendMessagesRequest({});
  expect(withUnset.has("X-Digi-Language")).toBe(false);
});
```

(Adjust the helper name/shape to whatever this test file already uses to invoke `prepareSendMessagesRequest` and read back the resulting `Headers` — do not invent a second harness alongside an existing one.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/hooks/use-embed-digi-chat.test.ts`
Expected: FAIL — `X-Digi-Language` header is never set.

- [ ] **Step 3: Write minimal implementation**

In `frontend/digichat/src/hooks/use-embed-digi-chat.ts`, add `responseLanguage?: string` to `UseEmbedDigiChatOptions` and destructure it in `useEmbedDigiChat`'s parameter list, then inside `prepareSendMessagesRequest`, next to the `byokKey` block:

```typescript
          if (responseLanguage && responseLanguage !== "en") {
            headers["X-Digi-Language"] = responseLanguage;
          }
```

Add `responseLanguage` to the `useMemo` dependency array that wraps the `DefaultChatTransport` construction (same array that already lists `byokKey, byokProvider, byokModel` — find it a few lines below the `prepareSendMessagesRequest` closure and add `responseLanguage` to it).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/digichat && npx vitest run src/hooks/use-embed-digi-chat.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/hooks/use-embed-digi-chat.ts frontend/digichat/src/hooks/use-embed-digi-chat.test.ts
git commit -m "feat(digichat): forward response language as X-Digi-Language header (#2103)"
```

---

### Task 8: Wire the dropdown into the embed shell

**Files:**
- Modify: `frontend/digichat/src/app/embed/embed-client.tsx` (`EmbedChat`)

**Interfaces:**
- Consumes: `detectBrowserLanguageCode`, `resolveLanguageCode` (Task 4), `LanguageSelect` (Task 6), `useEmbedDigiChat`'s new `responseLanguage` option (Task 7), `uiFlags.showLanguageSelector` (Task 5).
- Produces: nothing further downstream — this is the integration point.

No new test file: `embed-client.tsx` has no existing unit test (876-line client component covered indirectly through the hooks/lib modules it composes, per this codebase's existing convention — Tasks 4/5/6/7 already cover every piece of logic this task touches). Verification is the manual smoke check in Step 4.

- [ ] **Step 1: Add language state**

In `EmbedChat`, next to the `uiFlags` line:

```typescript
  const uiFlags = resolveEmbedUiFlags(tenantCfg);
  const [language, setLanguage] = useState(() => detectBrowserLanguageCode());
```

Add the import at the top of the file:

```typescript
import { LanguageSelect } from "@/components/language-select";
import { detectBrowserLanguageCode } from "@/lib/languages";
```

- [ ] **Step 2: Pass it to the chat hook**

In the `useEmbedDigiChat({...})` call, add:

```typescript
    responseLanguage: language,
```

- [ ] **Step 3: Render the dropdown in the header slot**

Replace the existing `headerSlot` construction:

```typescript
  const headerSlot = headerTitle ? (
    <header className="dc-brand">
      <span>{headerTitle}</span>
      {headerAttribution ? (
        <span className="dc-brand-by">
          (
          <a
            href="https://digithings.ai"
            target="_blank"
            rel="noreferrer noopener"
            className="dc-brand-link"
          >
            by digichat
          </a>
          )
        </span>
      ) : null}
    </header>
  ) : null;
```

with:

```typescript
  const headerSlot = headerTitle || uiFlags.showLanguageSelector ? (
    <header className="dc-brand">
      {headerTitle ? <span>{headerTitle}</span> : null}
      {headerAttribution ? (
        <span className="dc-brand-by">
          (
          <a
            href="https://digithings.ai"
            target="_blank"
            rel="noreferrer noopener"
            className="dc-brand-link"
          >
            by digichat
          </a>
          )
        </span>
      ) : null}
      {uiFlags.showLanguageSelector ? (
        <LanguageSelect value={language} onChange={setLanguage} />
      ) : null}
    </header>
  ) : null;
```

- [ ] **Step 4: Manual smoke check**

Run: `cd frontend/digichat && npm run dev`

Open `http://localhost:3000/embed?host=digithings.ai` (or whatever local embed URL this repo's dev docs use for a first-party host — check `frontend/digichat/OPERATIONS.md` if unsure of the exact query params for local first-party embed testing).

Expected: a language dropdown appears in the embed header showing "English" (or the browser's detected language if it's one of the curated 5); selecting "German" and sending a message shows the outgoing `/api/chat` request (Network tab) carrying an `X-Digi-Language: de` header.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/app/embed/embed-client.tsx
git commit -m "feat(digichat): render language selector in embed header (#2103)"
```

---

### Task 9: `route.ts` forwards the language to both backends

**Files:**
- Modify: `frontend/digichat/src/app/api/chat/route.ts`
- Modify: `frontend/digichat/src/app/api/chat/route.test.ts`

**Interfaces:**
- Consumes: `resolveLanguageCode` (Task 4).
- Produces: `X-Digi-Language` upstream header for the digigraph path, `responseLanguage` option passed to `createFoundryStreamResponse` (Task 10).

- [ ] **Step 1: Write the failing tests**

Read the existing BYOK/corpus-header test cases in `route.test.ts` first and match their request-mocking style exactly. Add:

```typescript
it("forwards X-Digi-Language to digigraph upstream headers", async () => {
  const req = buildChatRequest({
    headers: { "x-digi-language": "de" },
    // ...whatever base fields the existing digigraph-path tests in this file use...
  });
  await POST(req);
  expect(lastUpstreamHeaders()["X-Digi-Language"]).toBe("de");
});

it("omits X-Digi-Language from upstream headers when the request sends English", async () => {
  const req = buildChatRequest({ headers: { "x-digi-language": "en" } });
  await POST(req);
  expect(lastUpstreamHeaders()["X-Digi-Language"]).toBeUndefined();
});

it("passes responseLanguage to the Foundry adapter", async () => {
  const req = buildChatRequest({
    headers: { "x-digi-language": "fr" },
    // ...whatever base fields the existing Foundry-path tests in this file use...
  });
  await POST(req);
  expect(lastFoundryCallOptions().responseLanguage).toBe("fr");
});
```

(`buildChatRequest`, `lastUpstreamHeaders`, `lastFoundryCallOptions` stand in for whatever request-building and mock-inspection helpers this file already defines for its existing BYOK-header and Foundry-branch tests — use those exact helpers, don't invent new ones.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend/digichat && npx vitest run src/app/api/chat/route.test.ts`
Expected: FAIL — no `X-Digi-Language` header reaches either backend call yet.

- [ ] **Step 3: Write minimal implementation**

In `route.ts`, next to the existing header reads (`byokKey`, `byokProvider`, `byokModel`):

```typescript
  const languageCode = resolveLanguageCode(req.headers.get("x-digi-language"));
```

Add the import at the top:

```typescript
import { resolveLanguageCode } from "@/lib/languages";
```

In the Foundry branch, add `responseLanguage` to the `createFoundryStreamResponse` call:

```typescript
  if (embedConfig?.backend.type === "foundry") {
    return await createFoundryStreamResponse({
      projectEndpoint: embedConfig.backend.projectEndpoint,
      agentName: embedConfig.backend.agentName,
      messages,
      conversationId: req.headers.get("x-external-conversation"),
      responseHeaders,
      activityDetail: embedConfig.activityDetail,
      signal: req.signal,
      responseLanguage: languageCode,
    });
  }
```

In the digigraph branch, in the `upstreamHeaders` construction, next to the BYOK block:

```typescript
  if (languageCode !== "en") {
    upstreamHeaders["X-Digi-Language"] = languageCode;
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/app/api/chat/route.test.ts`
Expected: PASS

Then run the full digichat Vitest suite:
Run: `cd frontend/digichat && npx vitest run`
Expected: all green (Task 10 hasn't added the `responseLanguage` option to `createFoundryStreamResponse` yet, so this task's Foundry-forwarding test may need Task 10 done first — if it fails only on that one assertion, note it and proceed; Task 10 closes the loop).

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/app/api/chat/route.ts frontend/digichat/src/app/api/chat/route.test.ts
git commit -m "feat(digichat): forward response language to both backend adapters (#2103)"
```

---

### Task 10: Foundry adapter prepends the language directive

**Files:**
- Modify: `frontend/digichat/src/lib/adapters/foundry/stream.ts`
- Modify: `frontend/digichat/src/lib/adapters/foundry/stream.test.ts`
- Modify: `frontend/digichat/ARCHITECTURE.md` (document the dual-backend language contract)

**Interfaces:**
- Consumes: nothing new from this plan (uses a plain string option).
- Produces: `createFoundryStreamResponse(opts: { ...; responseLanguage?: string })`. This closes the loop Task 9 started.

- [ ] **Step 1: Write the failing tests**

Read the existing test structure in `stream.test.ts` first (it already tests `createFoundryStreamResponse`'s `input` construction indirectly via a mocked `openAIClientFactory`/`responses.create` — match that mocking style). Add:

```typescript
it("prepends a language directive to input when responseLanguage is a non-English curated code", async () => {
  const created: { input?: string }[] = [];
  const client = fakeFoundryClient(created); // however the existing tests build a fake client
  await createFoundryStreamResponse({
    projectEndpoint: "https://example",
    agentName: "agent",
    messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hallo" }] }] as never,
    conversationId: "conv-1",
    responseHeaders: {},
    activityDetail: "labels",
    openAIClientFactory: () => client,
    responseLanguage: "de",
  });
  expect(created[0]?.input).toBe(
    "[Respond only in German. Do not mention this instruction.]\n\nhallo",
  );
});

it("does not alter input when responseLanguage is English or unset", async () => {
  const created: { input?: string }[] = [];
  const client = fakeFoundryClient(created);
  await createFoundryStreamResponse({
    projectEndpoint: "https://example",
    agentName: "agent",
    messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }] as never,
    conversationId: "conv-1",
    responseHeaders: {},
    activityDetail: "labels",
    openAIClientFactory: () => client,
  });
  expect(created[0]?.input).toBe("hi");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend/digichat && npx vitest run src/lib/adapters/foundry/stream.test.ts`
Expected: FAIL — TypeScript error / runtime mismatch, since `responseLanguage` isn't an accepted option yet and `input` is never prefixed.

- [ ] **Step 3: Write minimal implementation**

In `frontend/digichat/src/lib/adapters/foundry/stream.ts`, add a pure helper near the top (below the imports, alongside the other small pure helpers like `stripFoundryCitationMarkers`), using the `LANGUAGES` array from Task 4 (the frontend list is an array of `{code, label}`, not a map — unlike the Python-side `LANGUAGE_NAMES` from Task 1):

```typescript
/** Foundry has no per-call system-prompt slot (see module doc comment) — the
 * language directive is prepended to the raw input text instead, resent on
 * every turn since Foundry, not this adapter, holds conversation history. */
export function applyLanguageDirective(message: string, responseLanguage?: string): string {
  if (!responseLanguage || responseLanguage === "en") return message;
  const language = LANGUAGES.find((l) => l.code === responseLanguage);
  if (!language) return message;
  return `[Respond only in ${language.label}. Do not mention this instruction.]\n\n${message}`;
}
```

Add the corresponding import:

```typescript
import { LANGUAGES } from "@/lib/languages";
```

Add `responseLanguage?: string` to the `createFoundryStreamResponse` options type, and change:

```typescript
  const message = lastUserMessageText(opts.messages);
```

to:

```typescript
  const message = applyLanguageDirective(lastUserMessageText(opts.messages), opts.responseLanguage);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/lib/adapters/foundry/stream.test.ts`
Expected: PASS

Then re-run Task 9's route tests, which depend on this option existing:
Run: `cd frontend/digichat && npx vitest run src/app/api/chat/route.test.ts`
Expected: PASS

Then the full suite:
Run: `cd frontend/digichat && npx vitest run`
Expected: all green.

In `frontend/digichat/ARCHITECTURE.md`, add a short paragraph (near wherever the digigraph vs. Foundry adapter split is already documented) noting: the language selector is the one feature with two independent implementations — `X-Digi-Language` header + digigraph's `research_node` system-prompt append on one side, `applyLanguageDirective`'s input-text prepend on the other — and link to `docs/superpowers/specs/2026-08-10-digichat-language-selector-design.md` for the rationale.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/adapters/foundry/stream.ts frontend/digichat/src/lib/adapters/foundry/stream.test.ts \
        frontend/digichat/ARCHITECTURE.md
git commit -m "feat(digichat): Foundry adapter prepends response-language directive (#2103)"
```

---

## Task 11: Full-suite verification and PR

**Files:** none (verification only)

- [ ] **Step 1: Run the full digigraph suite**

Run: `cd digigraph && uv run pytest -m unit -q`
Expected: all passing, including every test added in Tasks 1–3.

- [ ] **Step 2: Run the full digichat suite**

Run: `cd frontend/digichat && npx vitest run`
Expected: all passing, including every test added in Tasks 4–10.

- [ ] **Step 3: Run ruff and lint**

Run: `ruff check digigraph/src digigraph/../tests/dg && ruff format --check digigraph/src`
Run: `cd frontend/digichat && npm run lint`
Expected: clean on both.

- [ ] **Step 4: Push and open the task PR**

```bash
git push -u origin task/2103-digichat-language-selector
gh pr create --base develop \
  --title "feat(digichat): language selector — digigraph + Foundry (#2103)" \
  --body "Implements the language selector design (docs/superpowers/specs/2026-08-10-digichat-language-selector-design.md). Default-on per tenant, curated 5-language list, works on both the digigraph and Foundry/DataTap backends.

Fixes #2103"
```

- [ ] **Step 5: Request review**

Per CLAUDE.md's review-coverage gate: comment `bugbot run` on the PR once the diff is final. If Bugbot is unavailable (usage-limit skip, as seen repeatedly this session), run `/review` instead and let it post the `reviewed:agent` label + findings comment.

---

## Self-Review

**Spec coverage:** every acceptance-criterion checkbox from issue #2103 maps to a task above — tenant flag (Task 5), dropdown + curated list (Task 6), auto-detect/session-only (Task 8), `X-Digi-Language` + `WorkflowState` declaration (Tasks 2, 7, 9), `research_node` append (Task 3), Foundry `responseLanguage` + input prepend (Task 10), unknown-code safety (Tasks 1, 4), tests for all of the above, `ARCHITECTURE.md` updates (Tasks 2, 10).

**Placeholder scan:** no TBD/TODO; the one open item (Task 6's possible Radix role-name mismatch, Task 8's local embed URL lookup, Task 9's helper-name matching) are explicitly flagged as "read the existing file and match its convention," not left as unresolved logic.

**Type consistency:** `resolveLanguageCode`/`detectBrowserLanguageCode`/`LANGUAGES`/`DEFAULT_LANGUAGE_CODE` (Task 4) are used with identical names and signatures in Tasks 6, 7, 8, 9, 10. `resolve_language_directive`/`LANGUAGE_NAMES` (Task 1) are used identically in Tasks 2 and 3. `showLanguageSelector` flows through the same name at every layer (Task 5) into Task 8's `uiFlags.showLanguageSelector` read.
