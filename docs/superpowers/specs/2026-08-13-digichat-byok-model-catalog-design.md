# DigiChat BYOK model & provider catalog — design

- **Date:** 2026-08-13
- **Issue:** [#201](https://github.com/digithings-ai/digithings/issues/201) — "[FEATURE] Model selector settings panel — multi-provider BYOK"
- **Related:** [#8](https://github.com/digithings-ai/digithings/issues/8) (parent epic, BYOK flow shipped in PR #135), [#1873](https://github.com/digithings-ai/digithings/issues/1873) (closed 2026-08-10 — fixed the provider-allowlist truthfulness gap this spec builds on top of)
- **Components:** `frontend/digichat`, `digigraph`, `digillm`, `config/`

## Goal

Today's BYOK picker (`byok-cli-flow.tsx`) offers exactly 4 providers with a
flat, hand-written, unmaintained list of ~3 model presets each. This design:

1. Replaces the three independently-hardcoded provider lists (frontend UI, BFF
   validation route, digigraph's spend allowlist) with **one canonical
   catalog file**, closing the drift risk documented in [#1873](https://github.com/digithings-ai/digithings/issues/1873).
2. Adds a **live OpenRouter model catalog** with price-derived tiers (free /
   open-source / flagship / all) and a session-scoped custom multi-select,
   replacing the static 4-model OpenRouter preset array.
3. Extends live catalog fetching to OpenAI, Anthropic, and Gemini too, reusing
   calls the ping route already makes — no new upstream traffic for those three.
4. Adds a real, mechanical **tool-calling requirement gate** so a deployment
   like OCC (which depends on multi-round tool calls for retrieval) can
   require tool-capable models, while a deployment with no tools attached is
   unaffected.
5. Adds **x.ai (Grok)** as a fifth BYOK-routable provider, as the first
   provider added under the new single-source-of-truth mechanism — proving
   the mechanism, not just designing it on paper.

## Deviations from issue #201's acceptance criteria

Issue #201 has **seven** acceptance-criteria bullets. Four ship as literally
specified (settings panel accessible, provider selection persists, model
dropdown populated from live data, `ARCHITECTURE.md` updated). One ships
*mostly* as specified with a named carve-out. Two genuinely conflict with
already-shipped, already-tested constraints and are deferred rather than
built. Per this repo's own convention — see
[the phase3 unification spec's](2026-08-05-digichat-phase3-unification-design.md)
precedent of naming a deferred digivault-provider convergence under "Out of
scope" instead of silently dropping it — every divergence is named here:

| AC bullet (verbatim) | What ships instead | Why |
|---|---|---|
| "Supports: OpenAI, Anthropic, Gemini, Ollama (local), and a generic \"custom\" provider" | **Mostly ships**: OpenAI, Anthropic, Gemini, OpenRouter (already shipped) + **x.ai** (new). Ollama and generic-custom-URL are **deferred, explicitly out of scope** (see Out of scope). | digigraph runs server-side; a "custom base URL" is user-supplied and reachable from digigraph's own container network (SSRF-adjacent: internal service IPs, cloud metadata endpoints). Local Ollama is worse than SSRF-risky — it is **architecturally unreachable**: "localhost" from digigraph's perspective is digigraph's own container, never the visitor's machine. Neither can be a same-PR add to a hardcoded-provider allowlist; each needs its own design (client-side direct-fetch for Ollama; an SSRF-hardened proxy — scheme/host allowlist, no RFC1918/link-local/loopback, no redirects followed — for custom URLs). |
| "API key stored encrypted in DigiStore per user (never in localStorage)" | **Deviates.** Key stays **session-memory-only** (unchanged) — never DigiStore, never `localStorage`. | DigiStore [doesn't exist yet](../../vision/README.md) ("designed and specced but not yet implemented as standalone modules"). `docs/vision/digichat.md`'s claim that keys "persist in the digichat Drizzle/Postgres store today" is **false** against the shipped, tested code (`frontend/digichat/ARCHITECTURE.md:446-451`, the BYOK section, and `use-byok-key.ts`'s own doc comment) — this spec treats the shipped/tested behavior as authoritative and flags the vision doc for correction, not the other way around. |
| "Existing BYOK flow migrated to use this panel" | **Ships, reinterpreted.** The issue's own "Files affected" sketched a new `components/model-selector/` + `app/api/settings/` surface; this spec instead **extends the existing `byok-cli-flow.tsx` terminal stepper in place** (new tier tabs, live data, custom multi-select) rather than building a separate settings-panel component tree that the existing flow migrates into. | The existing stepper already carries the session-only-key precedent, the embed/main-app dual mounting, and the activation-gate logic this spec depends on; rebuilding it as a new component tree would duplicate all of that for no functional gain. Named here so the reinterpretation is visible, not implicit. |

"Provider selection persists across sessions" (AC4) is **not** a deviation —
it ships as specified, via the new non-secret cookie (see Decisions).

The issue's "Parallelizable: YES — pure frontend" and "Dependencies: None —
extend existing BYOK flow" are also incorrect as filed — the tool-calling gate
and the provider-catalog convergence both require `digigraph`/`digillm`
changes, and `llm_auth.py` is auth-adjacent (CLAUDE.md human gate).

## Decisions

| Question | Decision |
|---|---|
| Provider list source of truth | One file, `config/byok-providers.json` (see Data model). `digigraph` loads it directly at import time; the frontend keeps a **hand-written** TS constant (unchanged authoring experience) kept honest by a new CI cross-check test that reads the same JSON — no code generation step. |
| Key persistence | Unchanged: session-memory-only, never `localStorage`/`sessionStorage`/cookie/DB. This is a locked precedent, not re-litigated here. |
| Provider/model *selection* persistence | New: a non-secret cookie (`digichat_byok_pref`, provider+model id only) so a returning visitor's picker opens pre-selected. Never gates or replaces the "paste your key" step. |
| OpenRouter model tiers | Computed from the **live-fetched catalog's own pricing data**, not a hand-maintained model-id marker list — see "Why price-based tiers" below. Tiers: `free`, `opensource`, `flagship`, `all`, plus a session-scoped `custom` multi-select. |
| OpenAI / Anthropic / Gemini model lists | Also live-fetched, reusing the **same upstream call the ping already makes** (`/v1/models` for OpenAI and Anthropic, `/v1beta/models` for Gemini) — extended to return the full list instead of discarding it down to one display id. No new upstream request for these three. |
| OpenRouter key validation | Replace the current "burn a real 1-token completion" ping with `GET /api/v1/key` (an OpenRouter endpoint that validates a key and returns credit/rate-limit state with no completions cost) — validated independently of model choice, since model catalog listing on OpenRouter doesn't require a key at all. **Trade-off, accepted:** unlike a real completion, this never exercises OpenRouter's per-model authorization chain — a key restricted to a different model set, or one with $0 remaining credit, can plausibly return 200 here and only fail on the visitor's first real chat turn instead of at activation. The route's "ok" predicate must inspect the response's credit/limit fields (not just HTTP 200) to catch the exhausted-credit case; the model-restriction case is accepted as a real-turn failure, same class of surprise as an invalid `X-BYOK-Model` today. *(Verify this endpoint's exact current response shape against OpenRouter's live docs before implementing — this repo has no internet access to confirm it from this sandbox.)* |
| Tool-calling requirement gate | Deployment-grain, in `digiproject.yaml`: new `agents.require_tool_calls: bool`. **Not** embed-tenant-grain — tool availability is already a deployment property (`agents.allowed_tools`), and OCC's tool dependency is a property of *what tools that digigraph deployment has wired*, not of which tenant is asking. **Resolved as a floor, not a full override** (deliberately does *not* mirror `allowed_tools`' precedence shape — see Data flow for why). |
| Tool-capability signal for BYOK model choice | OpenRouter: use the live catalog's own capability signal (see Data model) rather than the existing `is_tool_use_capable_model()` slug heuristic — the heuristic stays untouched for Olympus, this is a separate, decoupled consumer. OpenAI/Anthropic/Gemini: treat every current-generation chat model as tool-capable (true today; no live per-model signal exists from those three providers' list endpoints) — no filtering applied. |
| New provider: x.ai | Added as the 5th entry in `config/byok-providers.json`. Already a registered *server-key* provider in `digillm._EXTERNAL_PROVIDERS` (`api.x.ai/v1`) — this only makes it BYOK-routable too. Fixed HTTPS base URL, so it carries none of the custom-provider/Ollama risk above. |
| digithings-web's duplicate picker (`providerSettings.ts`) | **Explicitly deferred**, not converged in this PR. It's a separate Next app with a materially weaker posture (localStorage-persisted keys) that this spec does not fix — named here so it isn't silently forgotten (see Out of scope). |

### Why price-based tiers, not a hand-maintained marker list

`digigraph/src/digigraph/model_config.py`'s `_FLAGSHIP_MODEL_ID_MARKERS`
(Olympus's own tiering) is a hardcoded substring list that has to be
hand-updated every time a new frontier model ships — exactly the staleness
`docs/LLM_PROVIDERS.md` already documents happening to free-tier model ids
(providers retiring `:free` slugs "with little notice"). A BYOK picker with
its own hardcoded marker list would rot the same way. Since the live
OpenRouter catalog fetch already returns each model's own `pricing` object,
tiering off that data is self-updating:

- **free** — `pricing.prompt == "0"` and `pricing.completion == "0"` (equivalent to today's `:free`-suffix check, but derived from data instead of a naming convention that not every free model follows).
- **opensource** — the entry carries a `hugging_face_id` (OpenRouter surfaces this for most open-weight models) *or* the model id's publisher segment matches a small, explicitly-maintained allowlist (`meta-llama`, `mistralai`, `qwen`, `deepseek`, `google/gemma`, `thudm`/`zai`, `moonshotai`) as a fallback for entries without one.
- **flagship** — prompt price at or above a configurable floor (proposed default: $3/1M input tokens, matching the cheapest current frontier tier per `docs/LLM_PROVIDERS.md`'s own cheap-paid-API table) — a number, not a name list, so a new frontier model qualifies automatically the day it's priced, no code change needed.
- **all** — the full unfiltered, searchable catalog.
- **custom** — a session-scoped user multi-select from `all`, held in the same React state as the rest of BYOK (never persisted beyond the tab).

*(The exact `pricing`/`hugging_face_id`/`supported_parameters` field names above are per OpenRouter's documented `/api/v1/models` response shape as of this repo's last provider-review cycle — re-verify against OpenRouter's live docs immediately before implementation, the same caveat `docs/LLM_PROVIDERS.md` already carries throughout.)*

## Architecture — approaches considered

### Provider-list single source of truth

| # | Approach | Verdict |
|---|---|---|
| **A** | **One JSON file** (`config/byok-providers.json`), loaded directly by `digigraph` (Python `json.load`, cached) and mirrored into a checked-in TS constant with a Vitest cross-check test asserting they match | **Chosen.** Lowest blast radius: no shared runtime coupling between Python and Node, no build-time codegen step to maintain, and it matches this repo's existing cross-check-test convention for exactly this class of drift (`languages.ts:1-7`'s documented "no shared module... must be mirrored by hand" pattern, enforced by a test rather than by shared code). |
| B | Runtime-fetch the JSON from a shared path at request time in both runtimes | Rejected. Adds a filesystem/network dependency to `digigraph`'s hot request path for data that changes maybe once a quarter; the JSON's whole value is being static and reviewable in a diff. |
| C | Generate the TS file from the JSON via a build script (`scripts/generate_byok_catalog.ts`) | Rejected for v1. Real fix for the "hand-sync" risk, but it's a second moving part (a script that must itself be re-run and can be forgotten) where a cross-check *test* achieves the same guarantee — CI fails loudly instead of silently drifting — with less machinery. Worth revisiting if the catalog grows past a handful of providers. |

### OpenRouter live fetch: where does it run

| # | Approach | Verdict |
|---|---|---|
| **A** | **New BFF route** `GET /api/byok/models?provider=openrouter` (only value `provider` accepts — 400 otherwise), calling OpenRouter's model-list endpoint **with no key forwarded at all** — it's a public, unauthenticated catalog | **Chosen.** No operator-side OpenRouter credential needed, and no visitor key needed either. Since the call needs nothing from the visitor, it can fire as soon as `openrouter` is picked as the provider (before the key step), so the tiered list is already warm by the time the model step renders — a prefetch, not something the model step blocks on. Same auth gate and rate limits as `/api/byok/test` apply to the *route itself* (see Security considerations), independent of whether OpenRouter needs a key. |
| B | Server-cached, periodically-refreshed catalog (operator's own key, cron-refreshed into a file or KV) | Rejected. Needs an operator OpenRouter key just to list models, plus a staleness/refresh story this repo has no infrastructure for yet (no scheduled-job runner wired to digichat). Revisit only if per-visitor live fetches become a real rate-limit problem. |
| C | Client-side direct fetch from the browser to OpenRouter, no BFF hop | Rejected. `next.config.ts`'s CSP (`connect-src 'self'`) would need loosening to allow `openrouter.ai` from the browser — a wider, permanent CSP change for what should be a narrow, server-mediated call. Every other outbound provider call in this repo already goes through a BFF route; breaking that pattern here is an unforced inconsistency. |

## Data model

### `config/byok-providers.json` (new — the canonical catalog)

```json
[
  {
    "id": "openrouter",
    "label": "OpenRouter",
    "keyPrefix": "sk-or-",
    "baseUrl": "https://openrouter.ai/api/v1",
    "requiresModel": true,
    "liveModelFetch": true,
    "fallbackModels": ["openai/gpt-4o-mini", "openai/gpt-4o", "anthropic/claude-sonnet-4", "google/gemini-2.0-flash"]
  },
  {
    "id": "openai",
    "label": "OpenAI",
    "keyPrefix": "sk-",
    "baseUrl": "https://api.openai.com/v1",
    "requiresModel": false,
    "liveModelFetch": true,
    "fallbackModels": ["gpt-4o-mini", "gpt-4o", "o4-mini"]
  },
  {
    "id": "anthropic",
    "label": "Anthropic",
    "keyPrefix": "sk-ant-",
    "baseUrl": "https://api.anthropic.com/v1",
    "requiresModel": true,
    "liveModelFetch": true,
    "fallbackModels": ["claude-sonnet-4-20250514", "claude-haiku-4-20250514", "claude-opus-4-20250514"]
  },
  {
    "id": "gemini",
    "label": "Gemini",
    "keyPrefix": "AI",
    "baseUrl": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "requiresModel": true,
    "liveModelFetch": true,
    "fallbackModels": ["gemini/gemini-2.0-flash", "gemini/gemini-2.5-flash", "gemini/gemini-2.5-pro"]
  },
  {
    "id": "xai",
    "label": "x.ai (Grok)",
    "keyPrefix": "xai-",
    "baseUrl": "https://api.x.ai/v1",
    "requiresModel": true,
    "liveModelFetch": false,
    "fallbackModels": ["grok-4-3", "grok-4.5"]
  }
]
```

`fallbackModels` replaces today's only-copy-of-the-truth preset arrays —
they become the **offline/rate-limited fallback**, shown only when live fetch
fails or (x.ai) isn't implemented yet. `keyPrefix` is verified against
`x.ai`'s and OpenRouter's own docs before implementation — the values above
are best-effort from this repo's existing `use-byok-key.ts` plus common
knowledge for x.ai, not independently re-confirmed in this session (no
internet access from this sandbox).

### digigraph — `_BYOK_BASE_URLS` becomes catalog-driven

`digigraph/src/digigraph/llm_auth.py:39-44`'s `_BYOK_BASE_URLS` dict literal
is replaced with a load from `config/byok-providers.json` **once, at module
import time** — deliberately *not* `model_config.py`'s `_load_model_modes`
mtime-recheck-per-call pattern (`model_config.py:262-291`). That pattern fits
`model_modes.yaml`, which is expected to change without a redeploy; the
provider catalog changes at the pace of a code review, same as any other
Python module-level constant. A missing file or a JSON/schema validation
failure **raises at import time**, crashing the process on startup — loud and
immediate in deploy logs/health checks — rather than degrading to an empty
allowlist that only surfaces as a wall of per-request 400s, and rather than
silently keeping a stale value on a redeploy that broke the file (both real
behaviors of the mtime-recheck pattern that would be wrong here: a missing
file logs nothing there, and a parse failure doesn't update the cache, so the
parse and the warning both repeat on every call while broken). `BYOK_ROUTABLE_PROVIDERS`
and `BYOK_MODEL_REQUIRED_PROVIDERS` (`llm_auth.py:45,47`) become derived from
the same one-time load instead of separate literals.

### digigraph — new tool-calling requirement field

```python
# digigraph/src/digigraph/project_config.py, next to get_allowed_tools (L407-412)
def get_require_tool_calls(self) -> bool:
    """Whether this deployment's tool loop must force tool_choice='required'. From agents.require_tool_calls."""
    return bool(self.agents.get("require_tool_calls"))
```

```python
# digigraph/src/digigraph/models.py, beside ChatCompletionRequest.allowed_tools (L66-69)
# and WorkflowRequest.allowed_tools (L88-94) — same Optional[bool] field shape,
# DIFFERENT resolution semantics (floor, not override — see Data flow):
require_tool_calls: bool | None = Field(
    None,
    description="Optional per-request signal that this completion needs tool_choice='required'. "
    "Also accepted via X-Require-Tool-Calls header. Combined with project agents.require_tool_calls "
    "and env DIGI_REQUIRE_TOOL_CALLS as a FLOOR (any true value wins) — unlike allowed_tools, this "
    "can only raise the requirement, never lower one the deployment already mandates.",
)
```

```python
# digillm/src/digillm/client.py — run_tools() signature (L1969-1981) gains one
# parameter, threaded into both _produce_turn call sites (L2046, L2056) in
# place of the current hardcoded literal:
def run_tools(
    model: str,
    messages: list[ChatCompletionMessage],
    tools: list[ToolDefinition],
    execute_tool: Callable[[str, ToolArguments], str | dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tool_rounds: int = 5,
    tool_choice: str = "auto",   # NEW — "auto" | "required"
    on_tool_step: Callable[[str, Any], None] | None = None,
    parallel_safe_tools: set[str] | None = None,
    stream_deltas: bool = False,
    search_parameters: dict[str, Any] | None = None,
) -> str:
```

### frontend — `use-byok-key.ts` model shape widens

`byokModelPresets(provider): readonly string[]` (`use-byok-key.ts:45-73`)
is superseded by a richer per-model shape once live data exists:

```ts
export type ByokModelOption = {
  id: string;
  label: string;
  tier?: "free" | "opensource" | "flagship";
  contextLength?: number;
  supportsTools?: boolean;
};
```

The flat `string[]` fallback (`fallbackModels` from the JSON catalog) stays
available as `ByokModelOption[]` with no `tier`/metadata, so the picker
degrades gracefully when live fetch fails — it never blocks on the network.

## Data flow

### Provider-catalog load (both runtimes, at startup/import)

```
config/byok-providers.json
  ├─ digigraph: llm_auth.py loads once at import — missing/invalid file raises, crashing startup
  │    → _BYOK_BASE_URLS / BYOK_ROUTABLE_PROVIDERS / BYOK_MODEL_REQUIRED_PROVIDERS derived from it
  │    → server.py's byok_header_context middleware unchanged — still 400s anything not in the loaded set
  └─ frontend: BYOK_PROVIDER_LIST / byokRequiresModel / byokModelPlaceholder in use-byok-key.ts
       stay hand-written TS (unchanged authoring experience) — a new Vitest test
       (`use-byok-key.catalog-parity.test.ts`) reads config/byok-providers.json
       from disk and asserts the TS provider list + requiresModel set match it
       exactly. CI fails the moment someone edits one side only.
```

### OpenRouter live model fetch + tiers + custom set

```
Step "provider" → user picks "openrouter"
  → fire-and-forget prefetch: GET /api/byok/models?provider=openrouter   (new BFF route)
      → GET https://openrouter.ai/api/v1/models   (no key forwarded — public catalog)
      → guard: reject/truncate above a fixed response-size ceiling before parsing;
        treat a non-array/unexpected-shape body as a fetch failure, not an exception
      → normalize + cap entry count: { id, label, pricing, hugging_face_id?, supported_parameters? }
      → bucket into free / opensource / flagship / all (pure function, unit-testable in isolation)
      → cached client-side for the rest of this session
  (this runs in parallel with step "key" below — the visitor is typing/pasting
   while it resolves, so it's almost always warm by the time step "model" renders)

Step "key" passes format validation → step "model"
  → if the prefetch above already resolved: tier tabs render immediately
  → if still pending: brief "fetching models" state, same non-blocking rule —
    on failure/timeout/malformed-response: falls back to today's fixed
    `fallbackModels` array from the catalog JSON; the flow never hard-fails
  → "custom" tab lets the user multi-select from "all" into a session-scoped set
  → user picks a model (or several, into "custom") → activation ping
    (GET /api/v1/key for OpenRouter specifically — see Decisions — instead
    of the current 1-token completion) → byokActivationGate → onActivate(...)
```

### OpenAI / Anthropic / Gemini live model list (reusing the existing ping call)

```
Step "key" → same POST /api/byok/test call that already runs today
  → testOpenAIKey/testAnthropicKey (byok/test/route.ts) already fetch
    /v1/models and today keep only `data.data[0].id` (route.ts:172,193)
  → testGeminiKey already fetches /v1beta/models and today keeps only
    `data.models[0].name`, stripped of its `models/` prefix (route.ts:251) —
    a different field path from the other two, same "discard everything but
    one id" pattern
  → CHANGE: return the full normalized list in the response body for all
    three, reading each provider's own actual array shape
    { ok, model, models: [{id, label}], error? }
  → frontend model step renders `models` when present, `fallbackModels` when
    the ping hasn't returned data yet or the field is empty
```

No second network round-trip for these three providers — same request,
more of its response is used.

### Tool-calling requirement gate

```
digiproject.yaml: agents.require_tool_calls: true   (e.g. OCC's config)
  → DigiProjectConfig.get_require_tool_calls() (project_config.py, new getter)
  → tool_policy.py: new resolver — a FLOOR, not a full override:
       effective = project agents.require_tool_calls
                   OR env DIGI_REQUIRE_TOOL_CALLS
                   OR req.require_tool_calls (or X-Require-Tool-Calls header)
    A request/header value can only turn the requirement ON when the
    deployment doesn't already mandate it — never OFF when it does.
  → graph/research.py:426-436, right where cfg.get_planning_mode() is already
    read at L438 — pass tool_choice="required" if resolved else "auto" into
    run_tools(...)
  → digigraph/llm_client.py:191-226 — its own run_tools() wrapper (imported
    into research.py as the name actually called) has no tool_choice
    parameter today either; it must gain one and forward it to
    _digillm_run_tools(...) (L215) or research.py's call raises TypeError
  → digillm/client.py's _produce_turn (L2046, L2056) uses the threaded value
    instead of the hardcoded "auto" literal
```

**Why this does *not* mirror `allowed_tool_names_for_workflow`'s
most-specific-wins precedence**, even though that's the obvious existing
pattern to copy: `allowed_tools` is safe to fully override per-request
because the resolved set is still bounded by tools actually registered on
the graph — a caller can *name* any tool it wants in an override, but can't
*invoke* one that was never wired, regardless of what the override says.
`require_tool_calls` has no equivalent ceiling; it is a bare boolean that
directly sets `tool_choice`. digigraph's own `/v1/chat/completions` endpoint
is consumed by callers outside digichat's control (its docstring notes it's
used as an Open WebUI-compatible model backend), so a full-override shape
here would let any caller send `X-Require-Tool-Calls: false` and
unconditionally defeat a deployment operator's mandatory tool-forcing policy
— e.g. disabling OCC's retrieval requirement — with no registry check and no
partial degradation. The floor shape closes that: a request can raise the
bar, never lower one the deployment set.

This gate governs the **tool loop itself** — it does not, on its own, stop a
visitor from BYOK-pasting a model that can't tool-call into a
tool-calls-required deployment. A UI-layer warning (badge, don't block) is
the natural next step, but it is **not implemented by this spec's plans**:
it would need `require_tool_calls` surfaced from digigraph's project config
into digichat's embed tenant-config response, and **no such bridge exists
today** — `api/embed/tenant-config/route.ts` is derived entirely from the
`DIGICHAT_EMBED_TENANTS` env var (`resolveVerifiedEmbedTenant` /
`toEmbedClientConfig`), with zero call into digigraph. (An earlier draft of
this section claimed this round-trip "already" happened for other
capability flags — verified false while planning implementation; corrected
here.) Building that bridge is its own design decision — a new digigraph
endpoint, a build-time/deploy-time config injection, or something else —
and is named here as explicit follow-up work, not silently assumed.

## Components touched

**Config (new):**
- `config/byok-providers.json` — the canonical catalog (Data model above).

**Backend (`digigraph/src/digigraph`):**
- `llm_auth.py` — `_BYOK_BASE_URLS` (L39-44) and the two derived sets (L45,47) load from the JSON catalog instead of literals; `push_byok_header`/`byok_provider_supported`/`byok_model_required` unchanged in behavior.
- `project_config.py` — new `get_require_tool_calls()` beside `get_allowed_tools()` (L407-412).
- `tool_policy.py` — new resolver, same file/module as `allowed_tool_names_for_workflow` (L12-40) but a **floor** (any-true-wins), not that function's full-override precedence — see Data flow for why the two must differ.
- `models.py` — `require_tool_calls: bool | None` on `ChatCompletionRequest` (beside L66-69) and `WorkflowRequest` (beside L88-94).
- `server.py` — header resolver for `X-Require-Tool-Calls`, mirroring `_resolve_allowed_tools_chat` (L783-790).
- `graph/research.py` — thread the resolved flag into `run_tools(...)` at the existing call site (L426-436).
- `llm_client.py` — its own `run_tools()` wrapper (L191-226), the actual name `research.py` calls, gains `tool_choice: str = "auto"` and forwards it to `_digillm_run_tools(...)` (L215) — found while planning implementation, not in the original draft's Components-touched list; without this, `research.py`'s call raises `TypeError` the moment it passes `tool_choice`.

**digillm (`digillm/src/digillm`):**
- `client.py` — `run_tools()` gains `tool_choice: str = "auto"` (L1969-1981), threaded into both `_produce_turn` call sites (L2046, L2056) in place of the hardcoded literal.

**Frontend (`frontend/digichat/src`):**
- `hooks/use-byok-key.ts` — `ByokModelOption` type added; `byokModelPresets` becomes the JSON catalog's `fallbackModels`, wrapped as options with no tier metadata.
- `app/api/byok/models/route.ts` — **new** BFF route: live OpenRouter catalog fetch + tier bucketing (pure function, separately unit-tested).
- `app/api/byok/test/route.ts` — `testOpenAIKey`/`testAnthropicKey`/`testGeminiKey` extended to return the full `models` array; OpenRouter's validation call switches from a 1-token completion to `GET /api/v1/key`.
- `components/byok-cli-flow.tsx` — model step renders tier tabs + custom multi-select when live data is present, falls back to a flat list otherwise; new brief "fetching models" transitional state.
- `lib/embed-tenants.ts` — no new tenant field needed (tool-calling requirement is deployment-, not tenant-, grain). The advisory "may not support tools" UI badge (a natural follow-up, not built by this spec's plans) would need `require_tool_calls` bridged from digigraph's project config into `api/embed/tenant-config/route.ts`'s response — **no such bridge exists today**; that route is derived entirely from the `DIGICHAT_EMBED_TENANTS` env var, with zero digigraph round-trip. Building it is its own design decision, named as follow-up work.
- A new Vitest `use-byok-key.catalog-parity.test.ts` reading `config/byok-providers.json` directly (Node `fs`, same pattern any other Node-side fixture test in this repo already uses) and asserting parity with the hand-written TS provider list.
- `ARCHITECTURE.md` (`frontend/digichat`) — update the BYOK section's provider table and note the new catalog file as the source of truth for the allowlist.
- `ARCHITECTURE.md` (`digigraph`) — document `agents.require_tool_calls` beside the existing `agents.allowed_tools` entry.

**Deferred / out of scope (named, not silently skipped):**
- `frontend/digithings-web/lib/providerSettings.ts` and `components/ProviderSettings.tsx` — not converged onto the new catalog in this PR.
- Ollama (local) and generic custom-base-URL providers — see "Deviations" above.
- DigiStore-encrypted key persistence — blocked on DigiStore shipping.

## Error handling

- **OpenRouter live fetch is slow** — bounded by the same `TIMEOUT_MS`/`abortOrMessage` pattern in `byok/test/route.ts`; falls back to `fallbackModels` from the catalog JSON, no user-visible error unless they explicitly retry.
- **OpenRouter live fetch returns a large-but-fast or malformed response** — a distinct failure class from "slow" that a wall-clock timeout alone doesn't bound: an explicit response-size ceiling rejects an oversized body before it's fully buffered/parsed, a cap on entry count bounds what the "all" tier ever echoes back, and a response that parses but isn't the expected shape (non-array `data`, missing fields) is treated as a fetch failure — same fallback path as a timeout, never an uncaught exception.
- **`config/byok-providers.json` is missing or fails validation on the digigraph side** — fails loudly at process startup (raises on import, per Data model) rather than starting a process that would silently serve every BYOK request a 400. A broken config is visible immediately in deploy health checks, not discovered request-by-request.
- **`agents.require_tool_calls` set but the visitor's BYOK model can't tool-call** — the request is **not** blocked server-side (heuristic signal, not a hard guarantee for 3 of 5 providers); it proceeds and the model simply won't call tools, same as any tool-incapable model attempted today. The UI badge is advisory, not enforced — matches this repo's existing stance that `is_tool_use_capable_model()` gates a *pool selection policy*, not a hard runtime block.
- **`config/byok-providers.json` and `use-byok-key.ts` drift** — caught in CI by the new parity test, not at runtime; runtime behavior when they *do* drift (before the test is fixed) is unchanged from today's status quo (UI offers a provider digigraph then 400s, or vice versa) — this spec closes the drift risk going forward, it doesn't add new runtime defense against it.

## Testing

- **Python:** `tool_policy.py` resolver unit test asserting the floor logic specifically — project `true` + request `false` still resolves `true` (the case the adversarial review caught as unsafe under a full-override design); project unset + request `true` resolves `true`; both unset resolves `false`. `run_tools()` test asserting `tool_choice="required"` reaches the underlying `_stream_completion_one_turn`/`completion` calls when threaded; `llm_auth.py` test asserting the catalog-loaded `_BYOK_BASE_URLS` matches `config/byok-providers.json`'s content (same file, loaded twice — parser round-trip, not hand-duplicated expectations); a startup test asserting a missing/malformed catalog file raises rather than degrading silently.
- **Frontend Vitest:** the new `use-byok-key.catalog-parity.test.ts`; a pure-function unit test for the tier-bucketing logic (free/opensource/flagship boundaries, including the `hugging_face_id`-absent fallback path); `app/api/byok/models/route.test.ts` mocking the OpenRouter fetch (success, timeout, malformed response); `byok/test/route.test.ts` extended for the new `models` array field and the `GET /api/v1/key` OpenRouter validation call.
- **Component:** this is the first BYOK spec to add real coverage for the gap the earlier investigation found — a `byok-cli-flow.test.tsx` exercising the stepper's provider→key→model→activate sequence with a mocked `fetch`, including the tier-tab / custom-multi-select interaction added here.
- Both `ARCHITECTURE.md` files updated in the same PR as their respective code changes, per this repo's standing rule.

## Security considerations

This spec adds a dedicated section here — the reference convention
(language-selector spec) folds its one security point inline into "Data
flow" instead — because this design's surface is genuinely different in
kind: a new server-mediated outbound proxy (`/api/byok/models`) and a bare
boolean that can weaken a deployment's tool-forcing policy are both the
class of change CLAUDE.md's human-gate list calls out explicitly (auth/JWT,
new network exposure). The adversarial review that produced this section
caught a real privilege-bypass in an earlier draft (see the tool-calling
bullet below) — evidence this class of design benefits from the extra
section rather than folding it away for shape-consistency alone.

- **Fixed literal base URLs, no exceptions.** The catalog-JSON approach keeps every BYOK base URL a **fixed literal reviewed in a diff** — nothing in this design accepts a user- or request-supplied base URL. That property is exactly what makes x.ai safe to add here and Ollama/custom unsafe to add here; this spec does not weaken it.
- **`GET /api/byok/models` — scope, auth, and rate limits are commitments, not incidental.** It never accepts or forwards a base URL parameter; the outbound URL is always the catalog's own `baseUrl`, never client-influenced. `provider` accepts **only `openrouter`** — 400 for any other value — it is not validated against the full 5-provider BYOK enum, since a naive `catalog[provider].baseUrl` implementation would silently turn this into an unauthenticated fetch proxy for all five upstream providers. It requires the identical auth gate as `/api/byok/test` (`requireDigiChatAuth` or a verified embed request), and — because the OpenRouter call itself needs no key, giving this route an even lower trigger bar than `/api/byok/test` — it needs its own rate limit on the authenticated/session path too, not just the embed IP limiter `/api/byok/test` applies today. Absent that, enough legitimate callers hammering one fixed destination risk tripping OpenRouter's own IP-based throttling against digichat's shared egress IP — a shared-fate degradation for every visitor, accepted here as a risk to monitor rather than solved outright (a global per-minute cap on outbound catalog fetches is the natural next step if it materializes).
- **OpenRouter validation trade-off, named not just assumed.** Switching from a completion to `GET /api/v1/key` is a real cost and blast-radius reduction (today's ping spends a real, if tiny, completion on every single model click — `selectModel` calls `runValidateAndActivate` immediately per click in the current `byok-cli-flow.tsx`). It is also a validation-strength regression: `/api/v1/key` never exercises OpenRouter's per-model authorization chain, so a key valid in general but restricted to a different model, or out of credit, can return 200 here and only fail on the visitor's first real chat turn. See the Decisions-table row for the accepted mitigation (inspect credit/limit fields, not bare HTTP 200).
- **Tool-calling gate is a floor, not an override — this was a real finding, fixed.** An earlier draft of this spec mirrored `allowed_tools`' full-override precedence for `require_tool_calls` (request/header wins over project config). That is unsafe here specifically: `allowed_tools` overrides are still bounded by the tool registry (a caller can't invoke what was never wired), but `require_tool_calls` is a bare boolean with no such ceiling, and digigraph's completions endpoint is reachable by non-digichat-controlled callers (Open WebUI-compatible clients). A full override would let any caller send `X-Require-Tool-Calls: false` and unconditionally defeat an operator's mandatory tool-forcing policy (e.g. OCC's retrieval gate) with one header. The design now resolves it as a floor (Data flow, "Tool-calling requirement gate") — a request can only raise the requirement, never lower one the deployment already set.
- `llm_auth.py`, `project_config.py`, and `models.py` changes here are auth-adjacent per CLAUDE.md's human-gate rule — this spec is the design step of that gate, not a substitute for the review itself before merge.

## Out of scope

- Ollama (local) and generic custom-base-URL BYOK providers — need their own dedicated design (client-side direct-fetch architecture for Ollama; SSRF-hardened proxy design for custom URLs). Tracked as follow-up work off this spec, not folded in here.
- DigiStore-encrypted, cross-device key persistence — blocked on DigiStore itself shipping (`docs/vision/README.md`).
- Converging `frontend/digithings-web`'s independent BYOK picker (`providerSettings.ts`) onto the new catalog.
- Rewriting Olympus's own `is_tool_use_capable_model()` heuristic or its `_FLAGSHIP_MODEL_ID_MARKERS` tiering — those stay as they are for the Atlas/Hermes pipelines; this spec only adds a separate, decoupled tiering path for the BYOK picker.
- A generic per-model tool-calling capability database — the OpenRouter live signal and "assume yes" for the other three are treated as good enough for this iteration; revisit if false negatives/positives turn out to matter in practice.
- The advisory "may not support tools" UI badge on the model picker — needs a digigraph-project-config-to-digichat-tenant-config bridge that does not exist today (see Data flow, "Tool-calling requirement gate"). Not implemented by either implementation plan derived from this spec.
- Rewriting the shared design tokens for the picker UI — issue #201's own comment flagged the (now-shipped, per #235 closing 2026-04-20) design-system epic as a soft dependency; this spec's UI changes should use those tokens where the picker touches shared chrome, but does not itself redesign the terminal-style BYOK stepper's visual language.

## Rollout note

This spec adds capability; it does not deploy anything on its own. Two
branch-staleness facts to check before cutting a `task/201-*` branch, per the
branching-model rule ("sync the module branch with develop before you branch
off it"):

- `module/digichat` is **93 commits behind** `develop` as of this writing — needs a sync PR before branching.
- `module/digigraph` is **3 commits behind** `develop` — small drift, but check again at branch-cut time since this repo iterates on `develop` continuously.

`digichat` and `digigraph` are both two-hop components (not in the
one-hop-to-`develop` exception list in `CLAUDE.md`), so implementation is
`task/201-slug` → `module/digichat` (+ a parallel `module/digigraph` task for
the backend half) → `develop`.

Given the auth-adjacent surface (`llm_auth.py`, `project_config.py`), this
lands under CLAUDE.md's human-gate rule regardless of `make score` results —
plan for explicit review before merge, not just a passing gate.

## Spec self-review

This draft went through one round of adversarial review by independent
readers (citation accuracy, completeness against the real issue text,
security, and structural convention) before this section was finalized. Two
things the review caught are worth recording, not just silently fixed:

- **A real privilege-bypass in the first draft.** The initial tool-calling
  gate design mirrored `allowed_tools`' full-override precedence, which would
  have let any caller send `X-Require-Tool-Calls: false` to unconditionally
  defeat a deployment's mandatory tool policy. Fixed to a floor (see Data
  flow / Security considerations). This is exactly the kind of finding the
  human-gate rule this spec cites exists to catch — recorded here so the
  eventual reviewer knows it was already found once, not to imply it needs
  no further scrutiny.
- **An acceptance-criteria miscount.** The first draft said "two of six" AC
  bullets deviate; issue #201 actually has seven, and the true split is four
  ship as specified, one ships with a named reinterpretation (AC6), and two
  deviate (AC2's Ollama/custom carve-out, AC3's DigiStore carve-out) — see
  Deviations. Corrected throughout.

Remaining self-checks:

- **Every AC in #201 addressed:** yes, against the corrected count of seven — see the Deviations table for the full accounting (4 ship as specified, 1 ships reinterpreted, 2 deviate with named reasons).
- **Every file:line citation** in this spec was re-read directly from the current working tree in this session (not taken on trust from an earlier summary) — `use-byok-key.ts`, `llm_auth.py`, `project_config.py`, `tool_policy.py`, `models.py`, `client.py`'s `run_tools`/`_produce_turn`, `research.py`'s call site, `byok/test/route.ts`'s per-provider extraction shapes — to catch drift between when the investigation ran and when this spec was written, and re-verified again after the adversarial review pass flagged specific citations to recheck.
- **Placeholders:** none left in decision rows; the two "verify against live docs" caveats (OpenRouter's exact field names, x.ai's key prefix) are flagged as such rather than asserted as fact, matching `docs/LLM_PROVIDERS.md`'s own "(uncertain)" convention for anything not independently confirmed this cycle.
- **Scope creep check:** the tool-calling gate is scoped to the mechanical `tool_choice` threading + deployment-grain config, not a rewrite of tool selection/registry logic. The provider catalog is scoped to the 4 shipped providers + x.ai, not every provider `docs/LLM_PROVIDERS.md` catalogs.
- **Known open question this spec does not resolve:** whether `agents.require_tool_calls: true` should also suppress the "(provider default)" no-model-chosen option for OpenAI BYOK (an empty model string can't be checked against any capability signal at all) — left to implementation-time judgment, since it's a small UX detail, not an architectural one.
