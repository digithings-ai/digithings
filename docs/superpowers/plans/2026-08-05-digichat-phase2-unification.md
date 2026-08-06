# digichat Phase 2 Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship full Phase 2 in one digichat PR — digivault provider port (2a) + digigraph rich `rag_sources`/`graph_update` mapping with dual-emit retirement (2b) — so auth and embed share one `data-digichatActivity` activity chain before Phase 3 cutover.

**Architecture:** Extend the Phase 1 allowlist (`ActivityDocument` + `ActivitySpan.brief`) and digichat-ui (`VaultHitSummary` + `brief` activity kind). Digigraph maps typed traces through that allowlist and stops writing `data-digigraphTrace`. A new `digivault-stream.ts` peer to `foundry-stream.ts` ports the Cloudflare agentic loop into Node route handlers (AI SDK UI stream, not NDJSON). Secrets stay as per-tenant env **name** refs. IP rate limit is 60/min via the existing in-memory `checkBffRateLimit` store (single-replica Node/Azure topology). Cloudflare Function stays until Phase 3; accent bug is out of scope.

**Tech Stack:** TypeScript, Next.js 16, Vercel AI SDK (`ai`), Vitest, `@digithings/digichat-ui`, Supabase REST RPC `search_architecture_notes`, OpenRouter free pool + BYOK (OpenRouter / OpenAI / Anthropic / Gemini).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-05-digichat-phase2-unification-design.md`. Phase 1 contract: `docs/superpowers/specs/2026-08-01-digichat-activity-protocol-design.md`.
- **One PR** covers 2a + 2b. Do not open a digivault-only or digigraph-only PR.
- **Do not touch** accent-bug files (`embed-accent-style*`, `use-embed-ui-params.ts`, unrelated embed page accent diffs) or branch `cursor/accent-bug-fix`.
- **Do not retire** the Cloudflare Function, `useStackChat`, `chatStream`, or digithings-web `/chat` (Phase 3).
- Presentation allowlist is `ActivitySpan` / `sanitizeActivitySpan` — undeclared keys (including `source_id`, scores, model ids, vault `body_markdown`) never copy onto activity parts.
- `reasoningDelta`, `documents`, and `brief` must not share one span — emit separate spans (projector early-returns on `reasoningDelta`).
- `activityDetail`: `off` → no parts; `labels` → strip **documents and brief** (and reasoning, Phase 1); set `documentsWithheld` when documents were present; brief-only spans become label/`trace` rows with no themes/questions (**no** `briefWithheld` flag — omit brief, keep label).
- Snippet budget: `MAX_SNIPPET_CHARS = 280` (named constant, ≤ `MAX_DOC_FIELD_CHARS` 300).
- Digivault secrets: only env **names** in tenant JSON (`supabaseUrlEnv`, `supabaseAnonKeyEnv`, `openRouterKeyEnv`); resolve `process.env[name]` at request time; missing → fail closed 5xx + server log; never echo values or missing contents to the browser.
- Env-name pattern: `/^[A-Z][A-Z0-9_]{0,127}$/` — rejects URLs and key-shaped strings.
- Digivault IP rate limit: **60 req / 60 s / IP**, wording `"rate limit exceeded — slow down a moment"`, store = existing in-memory `checkBffRateLimit` / `BoundedTTLMap` (not Workers KV).
- Browser protocol remains the **AI SDK UI message stream** — NDJSON mapping is internal.
- digichat-ui brief kind name: **`"brief"`**.
- Run digichat tests from `frontend/digichat` with `npx vitest run <path>`. Run digichat-ui tests from `frontend/digichat-ui` with `npx vitest run <path>`.
- Import `DigiChatActivity` with `import type` only in server modules.

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/digichat-ui/src/types.ts` | Extend `VaultHitSummary`; add `brief` to `DigiChatActivity` |
| `frontend/digichat-ui/src/components/ChatActivities.tsx` | Render tier/year/snippet hits + brief block |
| `frontend/digichat-ui/src/styles/session.css` | Hit meta + brief styles |
| `frontend/digichat-ui/src/ChatActivities.test.ts` | Unit coverage for new kinds |
| `frontend/digichat/src/lib/chat-activity.ts` | Allowlist for tier/year/snippet + brief; detail gate; projector |
| `frontend/digichat/src/lib/chat-activity.test.ts` | Allowlist / detail / projector tests |
| `frontend/digichat/src/lib/digigraph-activity-map.ts` | Typed `rag_sources` / `graph_update` → `ActivitySpan[]` |
| `frontend/digichat/src/lib/digigraph-activity-map.test.ts` | Mapper fixtures |
| `frontend/digichat/src/lib/stream-digigraph-trace.ts` | Use mapper; delete dual-emit / `emitLegacyTracePart` |
| `frontend/digichat/src/lib/stream-digigraph-trace.test.ts` | Assert no `data-digigraphTrace`; rich activity |
| `frontend/digichat/src/components/chat-panel.tsx` | Consume `data-digichatActivity` via `ChatActivities`; delete DigigraphTraceBlock / RagSourcesTrace / ResearchBriefTrace |
| `frontend/digichat/src/components/digigraph-trace.tsx` | **Delete** (unused legacy card) |
| `frontend/digichat/src/lib/embed-tenants.ts` | Parse/validate `digivault` backend variant |
| `frontend/digichat/src/lib/digivault-env.ts` | Resolve per-tenant env-name refs fail-closed |
| `frontend/digichat/src/lib/digivault-ip-rate-limit.ts` | 60/min/IP wrapper over `checkBffRateLimit` |
| `frontend/digichat/src/lib/digivault-vault.ts` | Supabase `search_architecture_notes` + context builder (body server-side only) |
| `frontend/digichat/src/lib/digivault-byok.ts` | Free pool + full BYOK route resolution (incl. Gemini) |
| `frontend/digichat/src/lib/digivault-stream.ts` | Agentic loop → AI SDK UI stream + activity spans |
| `frontend/digichat/src/lib/digivault-ndjson-adapter.ts` | CF NDJSON event → internal server events (parity) |
| `frontend/digichat/src/lib/fixtures/digivault/*` | Recorded NDJSON + vault RPC + golden spans/text |
| `frontend/digichat/src/app/api/chat/route.ts` | Branch `digivault`; stop passing `emitLegacyTracePart` |
| `frontend/digichat/src/hooks/use-byok-key.ts` (+ settings UI) | Add `gemini` to BYOK providers for parity |
| `frontend/digichat/ARCHITECTURE.md` | Document digivault backend + dual-emit removal |

---

### Task 1: digichat-ui — richer hits + `brief` kind

**Files:**
- Modify: `frontend/digichat-ui/src/types.ts`
- Modify: `frontend/digichat-ui/src/components/ChatActivities.tsx`
- Modify: `frontend/digichat-ui/src/styles/session.css`
- Create: `frontend/digichat-ui/src/ChatActivities.test.ts`

**Interfaces:**
- Consumes: existing `DigiChatActivity` / `VaultHitSummary`
- Produces:
  - `VaultHitSummary = { title: string; path: string; tier?: string; year?: number; snippet?: string }`
  - `DigiChatActivity` gains `| { kind: "brief"; themes: { label: string; summary: string }[]; questions?: string[] }`

- [ ] **Step 1: Write the failing test**

Create `frontend/digichat-ui/src/ChatActivities.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import type { DigiChatActivity, VaultHitSummary } from "./types";

describe("VaultHitSummary / DigiChatActivity Phase 2 shapes", () => {
  it("allows optional tier, year, snippet on hits", () => {
    const hit: VaultHitSummary = {
      title: "Auth",
      path: "docs/auth.md",
      tier: "peer_reviewed",
      year: 2024,
      snippet: "JWT exchange…",
    };
    expect(hit.tier).toBe("peer_reviewed");
    expect(hit.year).toBe(2024);
    expect(hit.snippet).toBe("JWT exchange…");
  });

  it("allows brief activity kind", () => {
    const row: DigiChatActivity = {
      kind: "brief",
      themes: [{ label: "Auth", summary: "RS256 tokens" }],
      questions: ["Which tenant?"],
    };
    expect(row.kind).toBe("brief");
    expect(row.themes).toHaveLength(1);
    expect(row.questions?.[0]).toBe("Which tenant?");
  });

  it("keeps thin {title,path} hits assignable", () => {
    const hit: VaultHitSummary = { title: "A", path: "p" };
    expect(hit).toEqual({ title: "A", path: "p" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat-ui && npx vitest run src/ChatActivities.test.ts`
Expected: FAIL — type errors / `kind: "brief"` not assignable (or PASS on shapes if types already updated — then proceed; if types missing, TypeScript in vitest should fail the brief assignment).

If the suite only typechecks at compile time and vitest runs JS without typecheck, force the contract by also asserting a switch exhaustiveness helper:

```ts
function assertNever(x: never): never {
  throw new Error(`unexpected: ${JSON.stringify(x)}`);
}

function kindLabel(a: DigiChatActivity): string {
  switch (a.kind) {
    case "status":
    case "tool_call":
    case "tool_result":
    case "reasoning":
    case "trace":
      return a.kind;
    case "brief":
      return "brief";
    default:
      return assertNever(a);
  }
}

it("exhaustively handles brief", () => {
  expect(
    kindLabel({
      kind: "brief",
      themes: [{ label: "T", summary: "S" }],
    })
  ).toBe("brief");
});
```

Expected before types change: FAIL compiling `case "brief"` / `assertNever`.

- [ ] **Step 3: Extend types**

In `frontend/digichat-ui/src/types.ts` replace:

```ts
export type VaultHitSummary = { title: string; path: string };

export type DigiChatActivity =
  | { kind: "status"; message: string }
  | { kind: "tool_call"; name: string; query: string }
  | {
      kind: "tool_result";
      name: string;
      query: string;
      hits: VaultHitSummary[];
      count: number;
    }
  | { kind: "reasoning"; text: string }
  | { kind: "trace"; label: string; done: boolean };
```

with:

```ts
export type VaultHitSummary = {
  title: string;
  path: string;
  tier?: string;
  year?: number;
  snippet?: string;
};

export type DigiChatActivity =
  | { kind: "status"; message: string }
  | { kind: "tool_call"; name: string; query: string }
  | {
      kind: "tool_result";
      name: string;
      query: string;
      hits: VaultHitSummary[];
      count: number;
    }
  | { kind: "reasoning"; text: string }
  | { kind: "trace"; label: string; done: boolean }
  | {
      kind: "brief";
      themes: { label: string; summary: string }[];
      questions?: string[];
    };
```

- [ ] **Step 4: Render richer hits + brief in ChatActivities**

In `frontend/digichat-ui/src/components/ChatActivities.tsx`, update `tool_result` hit list items and add `case "brief"`:

```tsx
case "tool_result":
  return (
    <div className="dc-act-result">
      <p className="dc-act-tool">
        <span className="dc-act-label">vault</span>{" "}
        {activity.count > 0
          ? `${activity.count} note${activity.count === 1 ? "" : "s"} for “${activity.query}”`
          : `no hits for “${activity.query}”`}
      </p>
      {activity.hits.length > 0 ? (
        <ul className="dc-act-hits">
          {activity.hits.map((h) => (
            <li key={h.path}>
              <span className="dc-act-hit-title">{h.title}</span>
              {h.tier ? <span className="dc-act-hit-tier">{h.tier}</span> : null}
              {typeof h.year === "number" ? (
                <span className="dc-act-hit-year">{h.year}</span>
              ) : null}
              <span className="dc-act-hit-path">{h.path}</span>
              {h.snippet ? <p className="dc-act-hit-snippet">{h.snippet}</p> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
case "brief":
  return (
    <details className="dc-act-brief">
      <summary>research brief</summary>
      {activity.themes.length > 0 ? (
        <ul className="dc-act-brief-themes">
          {activity.themes.map((t, i) => (
            <li key={`${t.label}-${i}`}>
              <span className="dc-act-brief-label">{t.label}</span>
              {t.summary ? ` — ${t.summary}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
      {activity.questions?.length ? (
        <div className="dc-act-brief-questions">
          <p className="dc-act-brief-q-heading">Next questions</p>
          <ol>
            {activity.questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ol>
        </div>
      ) : null}
    </details>
  );
```

Keep the `default: never` exhaustive check — `brief` must be handled so the switch still typechecks.

- [ ] **Step 5: Add CSS**

Append to `frontend/digichat-ui/src/styles/session.css`:

```css
.dc-act-hit-tier,
.dc-act-hit-year {
  margin-left: 0.35rem;
  color: var(--ink-mute);
  font-size: 0.88em;
}
.dc-act-hit-snippet {
  margin: 0.2rem 0 0;
  color: var(--ink-mute);
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.dc-act-brief {
  margin: 0.15rem 0 0;
}
.dc-act-brief summary {
  cursor: pointer;
  color: var(--ink-mute);
  font-weight: 500;
}
.dc-act-brief-themes {
  margin: 0.35rem 0 0;
  padding-left: 1rem;
}
.dc-act-brief-label {
  color: var(--ink-soft);
  font-weight: 600;
}
.dc-act-brief-questions {
  margin-top: 0.4rem;
}
.dc-act-brief-q-heading {
  margin: 0 0 0.2rem;
  font-size: 0.85em;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ink-mute);
}
.dc-act-brief-questions ol {
  margin: 0;
  padding-left: 1.1rem;
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend/digichat-ui && npx vitest run src/ChatActivities.test.ts`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/digichat-ui/src/types.ts \
  frontend/digichat-ui/src/components/ChatActivities.tsx \
  frontend/digichat-ui/src/styles/session.css \
  frontend/digichat-ui/src/ChatActivities.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat-ui): richer vault hits and research brief activity

EOF
)"
```

---

### Task 2: Allowlist — document fields + `brief` + detail gate

**Files:**
- Modify: `frontend/digichat/src/lib/chat-activity.ts`
- Modify: `frontend/digichat/src/lib/chat-activity.test.ts`

**Interfaces:**
- Consumes: digichat-ui `VaultHitSummary` / `DigiChatActivity` (type only)
- Produces:
  - `MAX_SNIPPET_CHARS = 280`
  - `MAX_BRIEF_THEMES = 8`, `MAX_BRIEF_QUESTIONS = 12`
  - `MAX_BRIEF_THEME_LABEL = 120`, `MAX_BRIEF_THEME_SUMMARY = 220`, `MAX_BRIEF_QUESTION_CHARS = 200`
  - `ActivityDocument = { title; path; tier?; year?; snippet? }`
  - `ActivityBrief = { themes: { label; summary }[]; questions?: string[] }`
  - `ActivitySpan.brief?: ActivityBrief`
  - `sanitizeActivitySpan` allowlists new fields
  - `applyActivityDetail` strips `documents` **and** `brief` at `labels` (sets `documentsWithheld` when docs present; does **not** invent `briefWithheld`)

- [ ] **Step 1: Write the failing tests**

Append to `frontend/digichat/src/lib/chat-activity.test.ts`:

```ts
import {
  MAX_SNIPPET_CHARS,
  MAX_BRIEF_THEMES,
  MAX_BRIEF_QUESTIONS,
  type ActivitySpan,
} from "./chat-activity";

describe("Phase 2 document fields + brief allowlist", () => {
  it("keeps tier, year, snippet on documents and drops undeclared doc keys", () => {
    const out = sanitizeActivitySpan(
      span({
        operation: "retrieve",
        status: "completed",
        documents: [
          {
            title: "Auth",
            path: "https://x/auth",
            tier: "peer_reviewed",
            year: 2024,
            snippet: "hello",
            source_id: "leak",
            score: 0.99,
            body_markdown: "# secret",
          },
        ],
      })
    );
    expect(out!.documents).toEqual([
      {
        title: "Auth",
        path: "https://x/auth",
        tier: "peer_reviewed",
        year: 2024,
        snippet: "hello",
      },
    ]);
  });

  it("caps snippet length", () => {
    const out = sanitizeActivitySpan(
      span({
        operation: "retrieve",
        status: "completed",
        documents: [
          {
            title: "T",
            path: "p",
            snippet: "s".repeat(MAX_SNIPPET_CHARS + 40),
          },
        ],
      })
    );
    expect(out!.documents![0].snippet).toHaveLength(MAX_SNIPPET_CHARS);
  });

  it("rejects non-finite year and non-string tier/snippet without dropping the doc", () => {
    const out = sanitizeActivitySpan(
      span({
        operation: "retrieve",
        status: "completed",
        documents: [{ title: "T", path: "p", tier: 1, year: "2024", snippet: 9 }],
      })
    );
    expect(out!.documents).toEqual([{ title: "T", path: "p" }]);
  });

  it("allowlists brief themes/questions and drops undeclared brief keys", () => {
    const out = sanitizeActivitySpan(
      span({
        operation: "chat",
        status: "completed",
        brief: {
          themes: [
            { label: "Auth", summary: "RS256", internal: true },
            ...Array.from({ length: MAX_BRIEF_THEMES + 3 }, (_, i) => ({
              label: `t${i}`,
              summary: `s${i}`,
            })),
          ],
          questions: Array.from({ length: MAX_BRIEF_QUESTIONS + 2 }, (_, i) => `q${i}`),
          model: "gpt",
        },
      })
    );
    expect(out!.brief!.themes).toHaveLength(MAX_BRIEF_THEMES);
    expect(out!.brief!.questions).toHaveLength(MAX_BRIEF_QUESTIONS);
    expect(Object.keys(out!.brief!).sort()).toEqual(["questions", "themes"]);
    expect(Object.keys(out!.brief!.themes[0]).sort()).toEqual(["label", "summary"]);
  });

  it("strips documents and brief at labels; preserves documentsWithheld honesty", () => {
    const full: ActivitySpan = {
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      documents: [{ title: "A", path: "p", tier: "t", year: 2020, snippet: "x" }],
      brief: { themes: [{ label: "T", summary: "S" }], questions: ["Q"] },
      reasoningDelta: "think",
    };
    const out = applyActivityDetail(full, "labels")!;
    expect(out.documents).toBeUndefined();
    expect(out.brief).toBeUndefined();
    expect(out.reasoningDelta).toBeUndefined();
    expect(out.documentsWithheld).toBe(true);
    expect("briefWithheld" in out).toBe(false);
  });

  it("brief-only span at labels becomes label row without themes", () => {
    const full: ActivitySpan = {
      operation: "chat",
      status: "completed",
      label: "Research brief",
      brief: { themes: [{ label: "T", summary: "S" }] },
    };
    const out = applyActivityDetail(full, "labels")!;
    expect(out).toEqual({
      operation: "chat",
      status: "completed",
      label: "Research brief",
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/chat-activity.test.ts`
Expected: FAIL — `MAX_SNIPPET_CHARS` / `brief` not defined / documents drop new fields

- [ ] **Step 3: Implement allowlist extensions**

In `frontend/digichat/src/lib/chat-activity.ts`:

1. Add constants after `MAX_REASONING_CHARS`:

```ts
export const MAX_SNIPPET_CHARS = 280;
export const MAX_BRIEF_THEMES = 8;
export const MAX_BRIEF_QUESTIONS = 12;
export const MAX_BRIEF_THEME_LABEL = 120;
export const MAX_BRIEF_THEME_SUMMARY = 220;
export const MAX_BRIEF_QUESTION_CHARS = 200;
```

2. Replace `ActivityDocument` / extend `ActivitySpan`:

```ts
export type ActivityDocument = {
  title: string;
  path: string;
  tier?: string;
  year?: number;
  snippet?: string;
};

export type ActivityBrief = {
  themes: { label: string; summary: string }[];
  questions?: string[];
};

export type ActivitySpan = {
  operation: "execute_tool" | "retrieve" | "chat";
  toolName?: string;
  query?: string;
  status: "started" | "completed" | "failed";
  label: string;
  documents?: ActivityDocument[];
  reasoningDelta?: string;
  documentsWithheld?: boolean;
  brief?: ActivityBrief;
};
```

3. Replace `documents()` to copy optional fields:

```ts
function documents(value: unknown): ActivityDocument[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out: ActivityDocument[] = [];
  for (const entry of value) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const record = entry as Record<string, unknown>;
    const title = str(record.title, MAX_DOC_FIELD_CHARS);
    const path = str(record.path, MAX_DOC_FIELD_CHARS);
    if (!title || !path) continue;
    const doc: ActivityDocument = { title, path };
    const tier = str(record.tier, MAX_DOC_FIELD_CHARS);
    if (tier) doc.tier = tier;
    if (typeof record.year === "number" && Number.isFinite(record.year)) {
      doc.year = Math.trunc(record.year);
    }
    const snippet = str(record.snippet, MAX_SNIPPET_CHARS);
    if (snippet) doc.snippet = snippet;
    out.push(doc);
    if (out.length === MAX_DOCUMENTS) break;
  }
  return out.length ? out : undefined;
}

function brief(value: unknown): ActivityBrief | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const record = value as Record<string, unknown>;
  if (!Array.isArray(record.themes)) return undefined;
  const themes: { label: string; summary: string }[] = [];
  for (const entry of record.themes) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const t = entry as Record<string, unknown>;
    const label = str(t.label, MAX_BRIEF_THEME_LABEL);
    const summary = str(t.summary, MAX_BRIEF_THEME_SUMMARY);
    if (!label || !summary) continue;
    themes.push({ label, summary });
    if (themes.length === MAX_BRIEF_THEMES) break;
  }
  if (!themes.length) return undefined;
  const out: ActivityBrief = { themes };
  if (Array.isArray(record.questions)) {
    const questions: string[] = [];
    for (const q of record.questions) {
      const s = str(q, MAX_BRIEF_QUESTION_CHARS);
      if (!s) continue;
      questions.push(s);
      if (questions.length === MAX_BRIEF_QUESTIONS) break;
    }
    if (questions.length) out.questions = questions;
  }
  return out;
}
```

4. In `sanitizeActivitySpan`, after documents / reasoning:

```ts
  const briefVal = brief(record.brief);
  if (briefVal) span.brief = briefVal;
```

5. Replace `applyActivityDetail` `labels` branch:

```ts
  const { documents, reasoningDelta: _reasoning, brief: _brief, ...rest } = span;
  void _reasoning;
  void _brief;
  return documents && documents.length > 0 ? { ...rest, documentsWithheld: true } : rest;
```

Also update the existing Phase 1 test `"strips documents and reasoning at labels"` if it still expects the old shape — keep it green with brief absent.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/lib/chat-activity.test.ts`
Expected: PASS (including prior Phase 1 cases — thin `{title,path}` still valid)

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/chat-activity.ts frontend/digichat/src/lib/chat-activity.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): allowlist document tier/year/snippet and brief

EOF
)"
```

---

### Task 3: Projector — rich hits + `brief` rows

**Files:**
- Modify: `frontend/digichat/src/lib/chat-activity.ts` (`toDigiChatActivity`)
- Modify: `frontend/digichat/src/lib/chat-activity.test.ts`

**Interfaces:**
- Consumes: `ActivitySpan` with optional `brief` / rich documents
- Produces: `toDigiChatActivity` maps:
  - retrieve hits → `tool_result.hits` preserving optional fields
  - `chat` span with `brief` → `{ kind: "brief", themes, questions }` (prefer brief over opaque `trace` when `brief` present)
  - `chat` without brief → existing `trace` behaviour
  - `labels`-stripped brief-only span (no `brief`) → `trace` from label

- [ ] **Step 1: Write the failing tests**

```ts
describe("toDigiChatActivity — Phase 2 rich hits + brief", () => {
  it("passes tier/year/snippet through tool_result hits", () => {
    const rows = toDigiChatActivity([
      {
        operation: "retrieve",
        status: "completed",
        label: "Sources",
        toolName: "file_search",
        query: "auth",
        documents: [
          {
            title: "Auth",
            path: "p",
            tier: "peer_reviewed",
            year: 2024,
            snippet: "JWT",
          },
        ],
      },
    ]);
    expect(rows).toEqual([
      {
        kind: "tool_result",
        name: "file_search",
        query: "auth",
        hits: [
          {
            title: "Auth",
            path: "p",
            tier: "peer_reviewed",
            year: 2024,
            snippet: "JWT",
          },
        ],
        count: 1,
      },
    ]);
  });

  it("projects brief spans onto kind brief", () => {
    const rows = toDigiChatActivity([
      {
        operation: "chat",
        status: "completed",
        label: "Research brief",
        brief: {
          themes: [{ label: "Auth", summary: "RS256" }],
          questions: ["Which tenant?"],
        },
      },
    ]);
    expect(rows).toEqual([
      {
        kind: "brief",
        themes: [{ label: "Auth", summary: "RS256" }],
        questions: ["Which tenant?"],
      },
    ]);
  });

  it("projects label-only chat (brief stripped) as trace", () => {
    expect(
      toDigiChatActivity([
        { operation: "chat", status: "completed", label: "Research brief" },
      ])
    ).toEqual([{ kind: "trace", label: "Research brief", done: true }]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/chat-activity.test.ts`
Expected: FAIL — brief projects as `trace` / hits lack fields (if documents already carry fields, first test may pass; brief test fails)

- [ ] **Step 3: Update projector**

In `toDigiChatActivity`, change the final `operation === "chat"` branch to:

```ts
    if (span.brief) {
      rows.push({
        kind: "brief",
        themes: span.brief.themes,
        ...(span.brief.questions ? { questions: span.brief.questions } : {}),
      });
      continue;
    }

    // operation === "chat": opaque upstream step…
    const key = span.label;
    const done = span.status !== "started";
    // ... existing collapse-by-label logic unchanged
```

Retrieve path already assigns `hits = span.documents ?? []` — once documents carry optional fields, they flow through. No change needed there beyond types.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/lib/chat-activity.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/chat-activity.ts frontend/digichat/src/lib/chat-activity.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): project brief spans and rich vault hits

EOF
)"
```

---

### Task 4: Digigraph mapper — `rag_sources` / `graph_update`

**Files:**
- Create: `frontend/digichat/src/lib/digigraph-activity-map.ts`
- Create: `frontend/digichat/src/lib/digigraph-activity-map.test.ts`

**Interfaces:**
- Consumes: `DigigraphTracePayload` (import type from `stream-digigraph-trace` **or** define a narrow input type in the mapper file to avoid cycles — prefer local `DigigraphTraceLike` matching `{ type; payload? }`)
- Produces:
  - `function mapDigigraphTraceToSpans(trace: DigigraphTraceLike, detail: ActivityDetail): ActivitySpan[]`
  - `rag_sources` → one `retrieve` span with documents (path from `source_id`/`doc_id`; title from metadata title / doi; tier/year/snippet)
  - `graph_update` with `research_brief` → one `chat` span with `brief` (themes + `profiling_questions` → questions), label `"Research brief"`
  - other types → existing opaque `chat` via `chatActivitySpan` semantics (label + status), returned as 0–1 span after detail gate
  - Always run outputs through `sanitizeActivitySpan` + `applyActivityDetail`

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, it, expect } from "vitest";
import { mapDigigraphTraceToSpans } from "./digigraph-activity-map";

describe("mapDigigraphTraceToSpans", () => {
  it("maps rag_sources to retrieve documents with tier/year/snippet", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "rag_sources",
        payload: {
          sources: [
            {
              source_id: "doc-1",
              snippet: "JWT exchange via digikey",
              metadata: {
                title: "Auth plane",
                evidence_tier: "peer_reviewed",
                publication_year: 2024,
              },
            },
            {
              doc_id: "doc-2",
              metadata: { doi_or_arxiv: "10.1/x", peer_reviewed: true },
            },
          ],
        },
      },
      "full"
    );
    expect(spans).toHaveLength(1);
    expect(spans[0]).toMatchObject({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "rag_sources",
      documents: [
        {
          title: "Auth plane",
          path: "doc-1",
          tier: "peer_reviewed",
          year: 2024,
          snippet: "JWT exchange via digikey",
        },
        {
          title: "10.1/x",
          path: "doc-2",
          tier: "peer_reviewed",
        },
      ],
    });
    expect(JSON.stringify(spans)).not.toContain("source_id");
  });

  it("maps graph_update research_brief to brief span", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "graph_update",
        payload: {
          research_brief: {
            themes: [{ label: "Auth", summary: "RS256 tokens" }],
          },
          profiling_questions: ["Which tenant?"],
        },
      },
      "full"
    );
    expect(spans).toEqual([
      {
        operation: "chat",
        status: "completed",
        label: "Research brief",
        brief: {
          themes: [{ label: "Auth", summary: "RS256 tokens" }],
          questions: ["Which tenant?"],
        },
      },
    ]);
  });

  it("strips documents and brief at labels", () => {
    const rag = mapDigigraphTraceToSpans(
      {
        type: "rag_sources",
        payload: {
          sources: [{ source_id: "d1", metadata: { title: "T" } }],
        },
      },
      "labels"
    );
    expect(rag[0].documents).toBeUndefined();
    expect(rag[0].documentsWithheld).toBe(true);

    const brief = mapDigigraphTraceToSpans(
      {
        type: "graph_update",
        payload: {
          research_brief: { themes: [{ label: "A", summary: "B" }] },
        },
      },
      "labels"
    );
    expect(brief[0].brief).toBeUndefined();
    expect(brief[0].label).toBe("Research brief");
  });

  it("maps opaque types to chat label spans", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "external_activity",
        payload: { label: "Searching…", status: "completed" },
      },
      "full"
    );
    expect(spans).toEqual([
      { operation: "chat", status: "completed", label: "Searching…" },
    ]);
  });

  it("emits nothing at off", () => {
    expect(
      mapDigigraphTraceToSpans(
        { type: "rag_sources", payload: { sources: [{ source_id: "d" }] } },
        "off"
      )
    ).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/digigraph-activity-map.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Implement mapper**

Create `frontend/digichat/src/lib/digigraph-activity-map.ts`:

```ts
import {
  applyActivityDetail,
  sanitizeActivitySpan,
  type ActivityDetail,
  type ActivityDocument,
  type ActivitySpan,
} from "@/lib/chat-activity";

export type DigigraphTraceLike = {
  type: string;
  payload?: Record<string, unknown>;
};

function tierFromMeta(meta: Record<string, unknown>): string | undefined {
  const t = meta.evidence_tier;
  if (typeof t === "string" && t.trim()) return t.trim();
  if (meta.peer_reviewed === true) return "peer_reviewed";
  return undefined;
}

function mapRagSources(payload: Record<string, unknown>): ActivitySpan | null {
  const sources = payload.sources;
  if (!Array.isArray(sources)) return null;
  const documents: ActivityDocument[] = [];
  for (const raw of sources) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
    const s = raw as Record<string, unknown>;
    const meta =
      s.metadata && typeof s.metadata === "object" && !Array.isArray(s.metadata)
        ? (s.metadata as Record<string, unknown>)
        : {};
    const path =
      (typeof s.source_id === "string" && s.source_id.trim()) ||
      (typeof s.doc_id === "string" && s.doc_id.trim()) ||
      "";
    const title =
      (typeof meta.title === "string" && meta.title.trim()) ||
      (typeof meta.doi_or_arxiv === "string" && meta.doi_or_arxiv.trim()) ||
      path;
    if (!path || !title) continue;
    const doc: ActivityDocument = { title, path };
    const tier = tierFromMeta(meta);
    if (tier) doc.tier = tier;
    if (typeof meta.publication_year === "number" && Number.isFinite(meta.publication_year)) {
      doc.year = Math.trunc(meta.publication_year);
    }
    if (typeof s.snippet === "string" && s.snippet.trim()) {
      doc.snippet = s.snippet.trim();
    }
    documents.push(doc);
  }
  if (!documents.length) return null;
  return {
    operation: "retrieve",
    status: "completed",
    label: "Sources",
    toolName: "rag_sources",
    documents,
  };
}

function mapGraphUpdate(payload: Record<string, unknown>): ActivitySpan | null {
  const briefRaw = payload.research_brief;
  if (!briefRaw || typeof briefRaw !== "object" || Array.isArray(briefRaw)) return null;
  const b = briefRaw as Record<string, unknown>;
  const themesIn = Array.isArray(b.themes) ? b.themes : [];
  const themes: { label: string; summary: string }[] = [];
  for (const entry of themesIn) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const t = entry as Record<string, unknown>;
    const label = typeof t.label === "string" ? t.label : "";
    const summary = typeof t.summary === "string" ? t.summary : "";
    if (!label.trim() || !summary.trim()) continue;
    themes.push({ label: label.trim(), summary: summary.trim() });
  }
  if (!themes.length) return null;
  const questions = Array.isArray(payload.profiling_questions)
    ? payload.profiling_questions.filter((q): q is string => typeof q === "string" && !!q.trim())
    : undefined;
  return {
    operation: "chat",
    status: "completed",
    label: "Research brief",
    brief: {
      themes,
      ...(questions?.length ? { questions } : {}),
    },
  };
}

function mapOpaque(trace: DigigraphTraceLike): ActivitySpan {
  const label =
    (typeof trace.payload?.label === "string" && trace.payload.label) || trace.type || "activity";
  const status = trace.payload?.status === "completed" ? "completed" : "started";
  return { operation: "chat", status, label };
}

export function mapDigigraphTraceToSpans(
  trace: DigigraphTraceLike,
  detail: ActivityDetail
): ActivitySpan[] {
  let raw: ActivitySpan | null = null;
  if (trace.type === "rag_sources") {
    raw = mapRagSources(trace.payload ?? {});
  } else if (trace.type === "graph_update") {
    raw = mapGraphUpdate(trace.payload ?? {});
    if (!raw) raw = mapOpaque(trace);
  } else {
    raw = mapOpaque(trace);
  }
  if (!raw) return [];
  const sanitized = sanitizeActivitySpan(raw);
  if (!sanitized) return [];
  const gated = applyActivityDetail(sanitized, detail);
  return gated ? [gated] : [];
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/lib/digigraph-activity-map.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/digigraph-activity-map.ts \
  frontend/digichat/src/lib/digigraph-activity-map.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): map digigraph rag_sources and graph_update to ActivitySpan

EOF
)"
```

---

### Task 5: Wire digigraph mapper (still dual-emit)

**Files:**
- Modify: `frontend/digichat/src/lib/stream-digigraph-trace.ts`
- Modify: `frontend/digichat/src/lib/stream-digigraph-trace.test.ts`

**Interfaces:**
- Consumes: `mapDigigraphTraceToSpans`
- Produces: each upstream trace writes 0..N `data-digichatActivity` parts from the mapper; **legacy `data-digigraphTrace` still dual-emits when `emitLegacyTracePart`** so chat-panel keeps working until Task 6

- [ ] **Step 1: Write the failing test**

Append to `stream-digigraph-trace.test.ts`:

```ts
it("emits rich retrieve activity for rag_sources on the gated path", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      [
        `data: ${JSON.stringify({
          choices: [
            {
              delta: {
                digigraph_trace: {
                  v: 1,
                  type: "rag_sources",
                  payload: {
                    sources: [
                      {
                        source_id: "doc-1",
                        snippet: "hello",
                        metadata: { title: "Auth", evidence_tier: "tier_a", publication_year: 2023 },
                      },
                    ],
                  },
                },
              },
            },
          ],
        })}\n\n`,
        "data: [DONE]\n\n",
      ].join(""),
      { status: 200, headers: { "content-type": "text/event-stream" } }
    )
  );

  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    upstreamBearer: "tok",
    activityDetail: "full",
    emitLegacyTracePart: false,
  });
  const body = await new Response(res.body).text();
  expect(body).toContain('"type":"data-digichatActivity"');
  expect(body).toContain('"operation":"retrieve"');
  expect(body).toContain('"tier":"tier_a"');
  expect(body).toContain('"year":2023');
  expect(body).not.toContain('"type":"data-digigraphTrace"');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/stream-digigraph-trace.test.ts`
Expected: FAIL — still emits flat `operation":"chat"` without retrieve/tier

- [ ] **Step 3: Wire mapper**

In `stream-digigraph-trace.ts`, replace the gated `chatActivitySpan(...)` block with:

```ts
import { mapDigigraphTraceToSpans } from "@/lib/digigraph-activity-map";
// remove unused chatActivitySpan import if no longer referenced

          if (opts.emitLegacyTracePart) {
            writer.write({
              type: "data-digigraphTrace",
              id: `dg-trace-${traceSeq++}`,
              data: payload,
            });
          }

          for (const span of mapDigigraphTraceToSpans(payload, opts.activityDetail)) {
            writer.write({
              type: ACTIVITY_PART_TYPE,
              id: `dg-activity-${activitySeq++}`,
              data: span,
            });
          }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/lib/stream-digigraph-trace.test.ts`
Expected: PASS (existing dual-emit test still passes)

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/stream-digigraph-trace.ts \
  frontend/digichat/src/lib/stream-digigraph-trace.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): emit rich digigraph activity spans from typed mapper

EOF
)"
```

---

### Task 6: Migrate chat-panel to `data-digichatActivity`

**Files:**
- Modify: `frontend/digichat/src/components/chat-panel.tsx`
- Delete: `frontend/digichat/src/components/digigraph-trace.tsx` (unused)

**Interfaces:**
- Consumes: `ACTIVITY_PART_TYPE`, `sanitizeActivitySpan`, `toDigiChatActivity`, `ChatActivities`
- Produces: MessageBody renders `ChatActivities` from activity parts; no `isDigigraphTracePart` / DigigraphTraceBlock / RagSourcesTrace / ResearchBriefTrace

- [ ] **Step 1: Write a focused regression test (or component-level extraction)**

Prefer extracting a pure helper next to the panel (or in `chat-activity.ts` already used by embed) — reuse `uiMessageToDigiChat` from `use-embed-digi-chat.ts` **or** duplicate the small projection in panel. To avoid coupling the auth panel to the embed hook, add `messageActivities(message: UIMessage): DigiChatActivity[]` export in `chat-activity.ts` (same logic as embed's activity branch without legacy fallback — auth path after Task 7 has no legacy parts).

Add to `chat-activity.test.ts`:

```ts
import type { UIMessage } from "ai";
import { messageActivities, ACTIVITY_PART_TYPE } from "./chat-activity";

it("messageActivities projects activity parts and ignores digigraphTrace", () => {
  const message = {
    id: "a1",
    role: "assistant",
    parts: [
      {
        type: ACTIVITY_PART_TYPE,
        data: {
          operation: "retrieve",
          status: "completed",
          label: "Sources",
          toolName: "rag_sources",
          documents: [{ title: "Auth", path: "doc-1", tier: "t", year: 2024 }],
        },
      },
      {
        type: "data-digigraphTrace",
        data: { type: "rag_sources", payload: { sources: [{ source_id: "should-not-render" }] } },
      },
    ],
  } as unknown as UIMessage;
  const rows = messageActivities(message);
  expect(rows.some((r) => r.kind === "tool_result")).toBe(true);
  expect(JSON.stringify(rows)).not.toContain("should-not-render");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/chat-activity.test.ts`
Expected: FAIL — `messageActivities` missing

- [ ] **Step 3: Implement `messageActivities` + migrate panel**

In `chat-activity.ts`:

```ts
import type { UIMessage } from "ai";

export function messageActivities(message: UIMessage): DigiChatActivity[] {
  const spans = message.parts
    .filter(
      (part): part is { type: typeof ACTIVITY_PART_TYPE; data: unknown } =>
        part.type === ACTIVITY_PART_TYPE
    )
    .map((part) => sanitizeActivitySpan(part.data))
    .filter((span): span is ActivitySpan => span !== null);
  return toDigiChatActivity(spans);
}
```

In `chat-panel.tsx`:

1. Remove DigigraphTracePayload import usage for rendering; remove `isDigigraphTracePart`, `tierLabel`, `RagSourcesTrace`, `ResearchBriefTrace`, `DigigraphTraceBlock`.
2. Import `ChatActivities` from `@digithings/digichat-ui` and `messageActivities` from `@/lib/chat-activity`.
3. In `MessageBody`, replace the digigraphTrace branch with a single activities render **once per message** (not per-part). Cleanest pattern:

```tsx
function MessageBody({ message, isStreaming }: { message: UIMessage; isStreaming?: boolean }) {
  // user branch unchanged…
  const activities = messageActivities(message);
  return (
    <div className="space-y-3">
      {activities.length ? <ChatActivities activities={activities} /> : null}
      {message.parts.map((part, i) => {
        // skip ACTIVITY_PART_TYPE and data-digigraphTrace parts (legacy noise during rollout)
        if (part.type === ACTIVITY_PART_TYPE || part.type === "data-digigraphTrace") return null;
        // existing reasoning / text / tool-invocation branches…
      })}
    </div>
  );
}
```

4. Delete `frontend/digichat/src/components/digigraph-trace.tsx`.

- [ ] **Step 4: Run tests**

Run:
```bash
cd frontend/digichat && npx vitest run src/lib/chat-activity.test.ts
```
Expected: PASS

Also run a typecheck if available: `cd frontend/digichat && npx tsc --noEmit -p tsconfig.json` (or `npm run build` if that is the project’s type gate). Fix any unused imports in chat-panel.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/chat-activity.ts \
  frontend/digichat/src/lib/chat-activity.test.ts \
  frontend/digichat/src/components/chat-panel.tsx
git rm frontend/digichat/src/components/digigraph-trace.tsx
git commit -m "$(cat <<'EOF'
feat(digichat): render auth chat activities from digichatActivity parts

EOF
)"
```

---

### Task 7: Delete dual-emit / legacy digigraphTrace writer

**Files:**
- Modify: `frontend/digichat/src/lib/stream-digigraph-trace.ts`
- Modify: `frontend/digichat/src/lib/stream-digigraph-trace.test.ts`
- Modify: `frontend/digichat/src/app/api/chat/route.ts`
- Modify: `frontend/digichat/src/hooks/use-embed-digi-chat.ts` (optional: keep legacy reader for one release — design says delete dual-emit **writer**; embed fallback reader may remain until Phase 3, but prefer updating tests that asserted dual-emit)
- Modify: `frontend/digichat/src/hooks/use-embed-digi-chat.test.ts` as needed

**Interfaces:**
- Consumes: mapper only
- Produces: `createDigigraphTraceStreamResponse` **without** `emitLegacyTracePart`; zero `data-digigraphTrace` on auth or embed

- [ ] **Step 1: Rewrite failing expectations**

Change the dual-emit test into:

```ts
it("never emits data-digigraphTrace on the authenticated path", async () => {
  // same fetch mock as the old dual-emit test
  const res = await createDigigraphTraceStreamResponse({
    messages: [userMessage("hi")],
    digigraphBaseUrl: "https://digigraph.internal",
    upstreamHeaders: {},
    responseHeaders: {},
    upstreamBearer: "tok",
    activityDetail: "full",
  });
  const body = await new Response(res.body).text();
  expect(body).not.toContain('"type":"data-digigraphTrace"');
  expect(body).toContain('"type":"data-digichatActivity"');
  expect(body).toContain('"operation":"chat"');
  expect(body).not.toContain('"workflow_id"');
});
```

Update every call site that passed `emitLegacyTracePart`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend/digichat && npx vitest run src/lib/stream-digigraph-trace.test.ts`
Expected: FAIL — still emits legacy part / type error on missing option

- [ ] **Step 3: Delete legacy writer**

1. Remove `emitLegacyTracePart` from opts type and implementation block.
2. In `route.ts`, stop passing `emitLegacyTracePart: !embedConfig`.
3. Leave embed `legacyTraceActivities` as a soft fallback for rolling deploys **or** remove it in the same PR — design success criterion is “zero emission or consumption” on auth; embed may keep reader. Prefer: keep reader (harmless) but ensure no writer remains. Update comments that say dual-emit is required.

- [ ] **Step 4: Run full related suites**

```bash
cd frontend/digichat && npx vitest run \
  src/lib/stream-digigraph-trace.test.ts \
  src/lib/chat-activity.test.ts \
  src/hooks/use-embed-digi-chat.test.ts \
  src/app/api/chat/route.test.ts
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/stream-digigraph-trace.ts \
  frontend/digichat/src/lib/stream-digigraph-trace.test.ts \
  frontend/digichat/src/app/api/chat/route.ts \
  frontend/digichat/src/hooks/use-embed-digi-chat.ts \
  frontend/digichat/src/hooks/use-embed-digi-chat.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): retire digigraphTrace dual-emit

EOF
)"
```

---

### Task 8: Embed tenant `digivault` backend + env-name validation

**Files:**
- Modify: `frontend/digichat/src/lib/embed-tenants.ts`
- Modify: `frontend/digichat/src/lib/embed-tenants.test.ts`
- Create: `frontend/digichat/src/lib/digivault-env.ts`
- Create: `frontend/digichat/src/lib/digivault-env.test.ts`

**Interfaces:**
- Produces:
  - `EmbedBackendConfig` adds `{ type: "digivault"; supabaseUrlEnv: string; supabaseAnonKeyEnv: string; openRouterKeyEnv: string }`
  - `ENV_NAME = /^[A-Z][A-Z0-9_]{0,127}$/`
  - Reject sibling raw URL/key fields for digivault
  - `resolveDigivaultEnv(backend): { supabaseUrl; supabaseAnonKey; openRouterKey } | never` — throws/`DigivaultEnvError` on missing; never returns secrets in error messages

- [ ] **Step 1: Write failing tests**

`embed-tenants.test.ts`:

```ts
it("accepts digivault backend with env-name refs", () => {
  process.env.DIGICHAT_EMBED_TENANTS = JSON.stringify({
    "docs.example.com": {
      slug: "docs",
      token: "tok",
      gateMode: "ungated",
      theme: "dark",
      attribution: true,
      backend: {
        type: "digivault",
        supabaseUrlEnv: "CORE_SUPABASE_URL",
        supabaseAnonKeyEnv: "CORE_SUPABASE_ANON_KEY",
        openRouterKeyEnv: "OPENROUTER_API_KEY",
      },
    },
  });
  // clear module cache / call load function used by suite
  const cfg = /* resolve host the same way existing tests do */;
  expect(cfg.backend).toEqual({
    type: "digivault",
    supabaseUrlEnv: "CORE_SUPABASE_URL",
    supabaseAnonKeyEnv: "CORE_SUPABASE_ANON_KEY",
    openRouterKeyEnv: "OPENROUTER_API_KEY",
  });
});

it("rejects digivault env names that look like URLs or keys", () => {
  expect(() =>
    parse(/* backend with supabaseUrlEnv: "https://x.supabase.co" */)
  ).toThrow(/env/i);
  expect(() =>
    parse(/* openRouterKeyEnv: "sk-or-v1-abc" */)
  ).toThrow(/env/i);
});
```

Match existing test helpers in the file (reload registry pattern) — do not invent a new loader; extend the suite’s established approach.

`digivault-env.test.ts`:

```ts
import { describe, it, expect, afterEach } from "vitest";
import { resolveDigivaultEnv, DigivaultEnvError } from "./digivault-env";

afterEach(() => {
  delete process.env.CORE_SUPABASE_URL;
  delete process.env.CORE_SUPABASE_ANON_KEY;
  delete process.env.OPENROUTER_API_KEY;
});

it("resolves env names to values", () => {
  process.env.CORE_SUPABASE_URL = "https://example.supabase.co";
  process.env.CORE_SUPABASE_ANON_KEY = "anon";
  process.env.OPENROUTER_API_KEY = "sk-or-v1-x";
  expect(
    resolveDigivaultEnv({
      type: "digivault",
      supabaseUrlEnv: "CORE_SUPABASE_URL",
      supabaseAnonKeyEnv: "CORE_SUPABASE_ANON_KEY",
      openRouterKeyEnv: "OPENROUTER_API_KEY",
    })
  ).toEqual({
    supabaseUrl: "https://example.supabase.co",
    supabaseAnonKey: "anon",
    openRouterKey: "sk-or-v1-x",
  });
});

it("fails closed without echoing values", () => {
  process.env.CORE_SUPABASE_URL = "https://example.supabase.co";
  // anon + openrouter missing
  try {
    resolveDigivaultEnv({
      type: "digivault",
      supabaseUrlEnv: "CORE_SUPABASE_URL",
      supabaseAnonKeyEnv: "CORE_SUPABASE_ANON_KEY",
      openRouterKeyEnv: "OPENROUTER_API_KEY",
    });
    expect.unreachable();
  } catch (e) {
    expect(e).toBeInstanceOf(DigivaultEnvError);
    const msg = String(e);
    expect(msg).not.toContain("https://example.supabase.co");
    expect(msg).toMatch(/not configured|missing/i);
  }
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd frontend/digichat && npx vitest run src/lib/embed-tenants.test.ts src/lib/digivault-env.test.ts
```
Expected: FAIL

- [ ] **Step 3: Implement**

`digivault-env.ts`:

```ts
export class DigivaultEnvError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DigivaultEnvError";
  }
}

export type DigivaultBackendConfig = {
  type: "digivault";
  supabaseUrlEnv: string;
  supabaseAnonKeyEnv: string;
  openRouterKeyEnv: string;
};

export type DigivaultResolvedEnv = {
  supabaseUrl: string;
  supabaseAnonKey: string;
  openRouterKey: string;
};

function readEnv(name: string): string {
  const value = process.env[name];
  if (typeof value !== "string" || !value.trim()) {
    throw new DigivaultEnvError("digivault backend is not configured");
  }
  return value.trim();
}

export function resolveDigivaultEnv(backend: DigivaultBackendConfig): DigivaultResolvedEnv {
  return {
    supabaseUrl: readEnv(backend.supabaseUrlEnv),
    supabaseAnonKey: readEnv(backend.supabaseAnonKeyEnv),
    openRouterKey: readEnv(backend.openRouterKeyEnv),
  };
}
```

In `embed-tenants.ts`, extend the union and validation:

```ts
export const EMBED_ENV_NAME = /^[A-Z][A-Z0-9_]{0,127}$/;

function requireEnvName(ctx: string, field: string, value: unknown): string {
  if (typeof value !== "string" || !EMBED_ENV_NAME.test(value)) {
    throw new Error(`${ctx}: digivault "${field}" must be an env var name (A-Z[A-Z0-9_]*)`);
  }
  return value;
}

// in validateEntry backend branch:
} else if (backend?.type === "digivault") {
  for (const banned of ["supabaseUrl", "supabaseAnonKey", "openRouterKey", "url"]) {
    if (banned in backend) {
      throw new Error(`${ctx}: digivault must not include raw "${banned}" — use *Env name refs`);
    }
  }
  backendCfg = {
    type: "digivault",
    supabaseUrlEnv: requireEnvName(ctx, "supabaseUrlEnv", backend.supabaseUrlEnv),
    supabaseAnonKeyEnv: requireEnvName(ctx, "supabaseAnonKeyEnv", backend.supabaseAnonKeyEnv),
    openRouterKeyEnv: requireEnvName(ctx, "openRouterKeyEnv", backend.openRouterKeyEnv),
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run same vitest command — Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/embed-tenants.ts \
  frontend/digichat/src/lib/embed-tenants.test.ts \
  frontend/digichat/src/lib/digivault-env.ts \
  frontend/digichat/src/lib/digivault-env.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): add digivault embed backend with per-tenant env-name refs

EOF
)"
```

---

### Task 9: Digivault IP rate limit (60/min)

**Files:**
- Create: `frontend/digichat/src/lib/digivault-ip-rate-limit.ts`
- Create: `frontend/digichat/src/lib/digivault-ip-rate-limit.test.ts`

**Interfaces:**
- Consumes: `checkBffRateLimit`, `clientIpForRateLimit` from `embed-ip-rate-limit.ts` (or re-export IP helper)
- Produces: `checkDigivaultIpRateLimit(ip: string): { allowed: true } | { allowed: false; retryAfterSec: number }` with default max **60**, window **60_000** ms, key `digivault-ip:${ip}`, overridable via `DIGICHAT_DIGIVAULT_IP_RATE_LIMIT_MAX`

- [ ] **Step 1: Write failing tests**

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { checkDigivaultIpRateLimit, DIGIVAULT_IP_RATE_LIMIT_MAX } from "./digivault-ip-rate-limit";

beforeEach(() => {
  // if module exposes resetForTests, call it; else use unique IPs per test
});

it("allows up to 60 requests per IP per window", () => {
  const ip = `203.0.113.${Math.floor(Math.random() * 200)}`;
  for (let i = 0; i < DIGIVAULT_IP_RATE_LIMIT_MAX; i++) {
    expect(checkDigivaultIpRateLimit(ip).allowed).toBe(true);
  }
  const blocked = checkDigivaultIpRateLimit(ip);
  expect(blocked.allowed).toBe(false);
  if (!blocked.allowed) expect(blocked.retryAfterSec).toBeGreaterThan(0);
});
```

- [ ] **Step 2: Run to verify fail**

Run: `cd frontend/digichat && npx vitest run src/lib/digivault-ip-rate-limit.test.ts`
Expected: FAIL — module missing

- [ ] **Step 3: Implement**

```ts
import { checkBffRateLimit, envPositiveInt } from "@/lib/bff-rate-limit";

export const DIGIVAULT_IP_RATE_LIMIT_MAX = envPositiveInt(
  "DIGICHAT_DIGIVAULT_IP_RATE_LIMIT_MAX",
  60
);
const WINDOW_MS = envPositiveInt("DIGICHAT_DIGIVAULT_IP_RATE_LIMIT_WINDOW_MS", 60_000);

export function checkDigivaultIpRateLimit(ip: string) {
  return checkBffRateLimit(`digivault-ip:${ip}`, DIGIVAULT_IP_RATE_LIMIT_MAX, WINDOW_MS);
}

export const DIGIVAULT_RATE_LIMIT_MESSAGE = "rate limit exceeded — slow down a moment";
```

- [ ] **Step 4: Run tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/digivault-ip-rate-limit.ts \
  frontend/digichat/src/lib/digivault-ip-rate-limit.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): add digivault 60/min IP rate limit

EOF
)"
```

---

### Task 10: Vault RPC + NDJSON→activity adapter (parity foundation)

**Files:**
- Create: `frontend/digichat/src/lib/digivault-vault.ts`
- Create: `frontend/digichat/src/lib/digivault-vault.test.ts`
- Create: `frontend/digichat/src/lib/digivault-ndjson-adapter.ts`
- Create: `frontend/digichat/src/lib/digivault-ndjson-adapter.test.ts`
- Create fixtures under `frontend/digichat/src/lib/fixtures/digivault/`

**Interfaces:**
- Produces:
  - `MAX_NOTE_CHARS = 1200`, `TOP_K = 4` (parity with CF)
  - `searchArchitectureNotes({ supabaseUrl, supabaseAnonKey, query }): Promise<VaultHit[]>` where `VaultHit = { vault_path; title; body_markdown }`
  - `buildToolContext(hits): { toolText: string; activityDocuments: ActivityDocument[] }` — **activity documents never include body**
  - `mapDigivaultNdjsonEvent(event): DigivaultServerEvent | null` where server events mirror foundry’s `{ text-delta | activity | quota_exhausted | error | done }`

- [ ] **Step 1: Write failing tests**

```ts
// digivault-vault.test.ts
it("projects activity documents without body_markdown", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify([
        {
          vault_path: "arch/digikey.md",
          title: "digikey",
          body_markdown: "# secret body",
        },
      ]),
      { status: 200 }
    )
  );
  const hits = await searchArchitectureNotes({
    supabaseUrl: "https://example.supabase.co",
    supabaseAnonKey: "anon",
    query: "digikey",
  });
  const { toolText, activityDocuments } = buildToolContext(hits);
  expect(toolText).toContain("secret body"); // model context may include truncated body
  expect(JSON.stringify(activityDocuments)).not.toContain("secret body");
  expect(JSON.stringify(activityDocuments)).not.toContain("body_markdown");
  expect(activityDocuments[0]).toEqual({ title: "digikey", path: "arch/digikey.md" });
});

// digivault-ndjson-adapter.test.ts
it("maps CF NDJSON kinds onto activity/text events", () => {
  expect(mapDigivaultNdjsonEvent({ type: "status", message: "Thinking…" })).toEqual({
    type: "activity",
    span: { operation: "chat", status: "started", label: "Thinking…" },
  });
  expect(
    mapDigivaultNdjsonEvent({ type: "tool_call", name: "search_digivault", query: "ports" })
  ).toEqual({
    type: "activity",
    span: {
      operation: "execute_tool",
      status: "started",
      label: "Searching digivault…",
      toolName: "search_digivault",
      query: "ports",
    },
  });
  expect(
    mapDigivaultNdjsonEvent({
      type: "tool_result",
      name: "search_digivault",
      query: "ports",
      hits: [{ title: "A", path: "a.md" }],
      count: 1,
    })
  ).toMatchObject({
    type: "activity",
    span: { operation: "retrieve", status: "completed", toolName: "search_digivault" },
  });
  expect(mapDigivaultNdjsonEvent({ type: "reasoning", delta: "…" })).toEqual({
    type: "activity",
    span: {
      operation: "chat",
      status: "started",
      label: "reasoning",
      reasoningDelta: "…",
    },
  });
  expect(mapDigivaultNdjsonEvent({ type: "content", delta: "Hi" })).toEqual({
    type: "text-delta",
    delta: "Hi",
  });
  expect(mapDigivaultNdjsonEvent({ type: "quota_exhausted", message: "out" })).toEqual({
    type: "quota_exhausted",
    message: "out",
  });
  expect(mapDigivaultNdjsonEvent({ type: "done" })).toEqual({ type: "done" });
});
```

Add a minimal recorded fixture file for Task 12, e.g. `fixtures/digivault/sample-turn.ndjson` + `sample-turn.golden.json` (spans + assistant text). Can be stubbed here and completed in Task 12.

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement vault + adapter**

Port `searchVault` / `buildContext` behaviour from `frontend/digithings-web/functions/api/chat.ts` (~339–414): POST `${supabaseUrl}/rest/v1/rpc/search_architecture_notes` with `{ query_text, match_count: TOP_K }`, headers `apikey` + `Authorization: Bearer ${anon}`. Truncate `body_markdown` with `MAX_NOTE_CHARS` **only in toolText**. Activity documents: `{ title, path: vault_path }` only.

Adapter maps as in the tests. For `tool_result`, also emit a completed `execute_tool` companion only if needed by projector — prefer Foundry’s pattern: `execute_tool` started + `retrieve` completed is enough when the stream emits both (CF already emits tool_call then tool_result).

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/digivault-vault.ts \
  frontend/digichat/src/lib/digivault-vault.test.ts \
  frontend/digichat/src/lib/digivault-ndjson-adapter.ts \
  frontend/digichat/src/lib/digivault-ndjson-adapter.test.ts \
  frontend/digichat/src/lib/fixtures/digivault/
git commit -m "$(cat <<'EOF'
feat(digichat): digivault vault RPC helper and NDJSON activity adapter

EOF
)"
```

---

### Task 11: Digivault BYOK + free pool

**Files:**
- Create: `frontend/digichat/src/lib/digivault-byok.ts`
- Create: `frontend/digichat/src/lib/digivault-byok.test.ts`
- Modify: `frontend/digichat/src/hooks/use-byok-key.ts` (add `gemini`)
- Modify: `frontend/digichat/src/components/byok-settings-panel.tsx` and embed BYOK UI provider lists to include `gemini`

**Interfaces:**
- Produces:
  - `ProviderId = "openrouter" | "openai" | "anthropic" | "gemini"`
  - `MODEL_POOL` identical to CF (three free OpenRouter models)
  - `resolveDigivaultLlmRoute({ byokKey, byokProvider, byokModel, openRouterKey }): LlmRoute | { error: string; status: 400 | 503 }`
  - Validation messages match CF (no key material echoed)
  - Gemini via OpenAI-compat URL `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`

- [ ] **Step 1: Write failing tests** for validate + resolve (free pool when no BYOK; 400 on bad key prefix; gemini route URL; anthropic kind)

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Port `validateByokKey` / `resolveRoute` / `DEFAULT_BYOK_MODEL` / `MODEL_POOL` / `QUOTA_MESSAGE` from CF `functions/api/chat.ts` into `digivault-byok.ts`. Extend `BYOKProvider` with `"gemini"` and `validateBYOKKey` (`startsWith("AI")`). Update settings provider buttons.

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/digivault-byok.ts \
  frontend/digichat/src/lib/digivault-byok.test.ts \
  frontend/digichat/src/hooks/use-byok-key.ts \
  frontend/digichat/src/components/byok-settings-panel.tsx \
  frontend/digichat/src/app/embed/page.tsx
git commit -m "$(cat <<'EOF'
feat(digichat): digivault BYOK routes including Gemini and free pool

EOF
)"
```

Note: only touch `embed/page.tsx` for the BYOK provider list (`gemini`) — **do not** edit accent-related code.

---

### Task 12: Digivault stream — agentic loop → AI SDK UI message stream

**Files:**
- Create: `frontend/digichat/src/lib/digivault-stream.ts`
- Create: `frontend/digichat/src/lib/digivault-stream.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export async function createDigivaultStreamResponse(opts: {
    messages: UIMessage[];
    env: DigivaultResolvedEnv;
    responseHeaders: Record<string, string>;
    activityDetail: ActivityDetail;
    byokKey?: string;
    byokProvider?: string;
    byokModel?: string;
    signal?: AbortSignal;
    /** test seam */
    fetchImpl?: typeof fetch;
  }): Promise<Response>;
  ```
- Behaviour: ≤ `MAX_TOOL_ROUNDS` (3) tool rounds; `search_digivault` → vault helper; emit AI SDK text + `ACTIVITY_PART_TYPE` via `sanitizeActivitySpan` + `applyActivityDetail`; `quota_exhausted` → user-safe status/error path (set controller `quotaPrompt` equivalent via a dedicated data part **or** text + activity status — prefer writing `{ type: ACTIVITY_PART_TYPE, data: { operation:"chat", status:"failed", label: QUOTA_MESSAGE } }` plus a short text delta with `QUOTA_MESSAGE`; mirror CF UX without NDJSON); never stream upstream bodies; vault body only in tool messages.

Port control flow from CF `runAgenticLoopStream` (`functions/api/chat.ts` ~782–908) and LLM call helpers (~459–774). Prefer keeping OpenAI-compat + Anthropic helpers in `digivault-stream.ts` or a private `digivault-llm.ts` if the file exceeds ~400 lines — split is encouraged.

- [ ] **Step 1: Write failing stream tests** with mocked `fetchImpl` / injectable loop:

```ts
it("writes activity parts and text deltas for a tool+answer turn", async () => {
  // Mock LLM: first response tool_calls search_digivault; vault RPC returns one hit;
  // second response streams content tokens; done.
  const res = await createDigivaultStreamResponse({ /* … */ activityDetail: "full" });
  const body = await new Response(res.body).text();
  expect(body).toContain('"type":"data-digichatActivity"');
  expect(body).toContain("search_digivault");
  expect(body).not.toContain("body_markdown");
  expect(body).not.toContain("# secret");
});

it("returns generic browser error and logs upstream failures", async () => {
  const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});
  // force LLM fetch 500 with secret traceback
  const res = await createDigivaultStreamResponse({ /* … */ });
  const body = await new Response(res.body).text();
  expect(body).not.toContain("Traceback");
  expect(body).toMatch(/unavailable|try again/i);
  expect(errorLog).toHaveBeenCalled();
});

it("honours activityDetail labels (no documents on wire)", async () => {
  // tool_result with hits under labels → activity has documentsWithheld / no documents
});
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `createDigivaultStreamResponse`** using `createUIMessageStream` / `createUIMessageStreamResponse` exactly like `foundry-stream.ts`. Emit spans through sanitize + detail gate. Reuse SYSTEM_PROMPT + TOOLS from CF verbatim.

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/digivault-stream.ts \
  frontend/digichat/src/lib/digivault-stream.test.ts \
  frontend/digichat/src/lib/digivault-llm.ts  # if split
git commit -m "$(cat <<'EOF'
feat(digichat): digivault agentic stream provider

EOF
)"
```

---

### Task 13: Wire digivault into `/api/chat` + fixture parity gate

**Files:**
- Modify: `frontend/digichat/src/app/api/chat/route.ts`
- Modify: `frontend/digichat/src/app/api/chat/route.test.ts`
- Create/complete: `frontend/digichat/src/lib/fixtures/digivault/*`
- Create: `frontend/digichat/src/lib/digivault-parity.test.ts`
- Modify: `frontend/digichat/ARCHITECTURE.md`

**Interfaces:**
- Route branch (after auth / shared rate limits, peer to foundry):
  1. If `embedConfig?.backend.type === "digivault"` (and any future auth-path digivault config if added the same way):
  2. `checkDigivaultIpRateLimit(clientIp)` → 429 with `DIGIVAULT_RATE_LIMIT_MESSAGE`
  3. `resolveDigivaultEnv(backend)` → catch `DigivaultEnvError` → 503 safe JSON
  4. `return createDigivaultStreamResponse({…})`
- Fixture parity: replay recorded CF NDJSON through `mapDigivaultNdjsonEvent` (+ optional vault RPC fixture) → golden `ActivitySpan[]` sequence and concatenated assistant text. **Behaviour parity, not byte-identical streams.**

- [ ] **Step 1: Write route + parity failing tests**

```ts
it("routes digivault backend to createDigivaultStreamResponse", async () => { /* mock tenant + spy */ });
it("returns 429 with digivault rate-limit wording", async () => { /* … */ });
it("returns 503 when digivault env names are unresolved", async () => { /* … */ });

// digivault-parity.test.ts
it("matches golden activity sequence for recorded CF turn", async () => {
  const ndjson = await readFile(/* fixture */, "utf8");
  const events = ndjson.trim().split("\n").map((l) => JSON.parse(l));
  const spans: ActivitySpan[] = [];
  let text = "";
  for (const ev of events) {
    const mapped = mapDigivaultNdjsonEvent(ev);
    if (!mapped) continue;
    if (mapped.type === "text-delta") text += mapped.delta;
    if (mapped.type === "activity") {
      const s = sanitizeActivitySpan(mapped.span);
      if (s) spans.push(s);
    }
  }
  const golden = JSON.parse(await readFile(/* golden */, "utf8"));
  expect(spans).toEqual(golden.spans);
  expect(text).toBe(golden.text);
});
```

Record fixtures by capturing one real CF turn (or hand-author a minimal realistic NDJSON from CF event shapes). Include a vault RPC response fixture asserting activity docs never carry body.

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Wire route.ts**

```ts
import { createDigivaultStreamResponse } from "@/lib/digivault-stream";
import { resolveDigivaultEnv, DigivaultEnvError } from "@/lib/digivault-env";
import {
  checkDigivaultIpRateLimit,
  DIGIVAULT_RATE_LIMIT_MESSAGE,
} from "@/lib/digivault-ip-rate-limit";
import { clientIpForRateLimit } from "@/lib/embed-ip-rate-limit";

// after external-relay / before foundry (or after foundry — order must be explicit):
if (embedConfig?.backend.type === "digivault") {
  const ip = clientIpForRateLimit(req);
  const rl = checkDigivaultIpRateLimit(ip);
  if (!rl.allowed) {
    return rateLimitedResponse(DIGIVAULT_RATE_LIMIT_MESSAGE, rl.retryAfterSec);
  }
  let env;
  try {
    env = resolveDigivaultEnv(embedConfig.backend);
  } catch (e) {
    if (e instanceof DigivaultEnvError) {
      console.error("[digivault] env resolution failed");
      return new Response(JSON.stringify({ error: "chat_not_configured" }), {
        status: 503,
        headers: { "content-type": "application/json" },
      });
    }
    throw e;
  }
  return createDigivaultStreamResponse({
    messages,
    env,
    responseHeaders,
    activityDetail: embedConfig.activityDetail,
    byokKey,
    byokProvider,
    byokModel,
    signal: req.signal,
  });
}
```

Update `ARCHITECTURE.md`: digivault backend, env-name secrets, dual-emit removed, digigraph mapper, rate limit, CF still live until Phase 3, accent out of scope.

- [ ] **Step 4: Run suites**

```bash
cd frontend/digichat && npx vitest run \
  src/app/api/chat/route.test.ts \
  src/lib/digivault-parity.test.ts \
  src/lib/digivault-stream.test.ts \
  src/lib/stream-digigraph-trace.test.ts \
  src/lib/chat-activity.test.ts \
  src/lib/foundry-stream.test.ts
cd frontend/digichat-ui && npx vitest run
```
Expected: PASS — Foundry thin-document regression still green

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/app/api/chat/route.ts \
  frontend/digichat/src/app/api/chat/route.test.ts \
  frontend/digichat/src/lib/digivault-parity.test.ts \
  frontend/digichat/src/lib/fixtures/digivault/ \
  frontend/digichat/ARCHITECTURE.md
git commit -m "$(cat <<'EOF'
feat(digichat): wire digivault provider and fixture parity gate

EOF
)"
```

---

## Self-review (plan vs design)

| Design requirement | Task(s) |
|---|---|
| Extend ActivityDocument tier/year/snippet + snippet cap | Task 2 (`MAX_SNIPPET_CHARS = 280`) |
| ActivitySpan.brief allowlist | Task 2 |
| digichat-ui richer VaultHitSummary + brief rendering | Task 1 (`kind: "brief"`) |
| Projector maps brief + rich hits | Task 3 |
| Digigraph rag_sources / graph_update mapper | Task 4–5 |
| Delete dual-emit / DigigraphTraceBlock / legacy writer | Task 6–7 |
| Digivault provider peer to foundry | Task 10–13 |
| Per-tenant env-name refs; fail closed | Task 8 |
| Full BYOK + free pool + quota_exhausted + Gemini | Task 11–12 |
| IP rate limit 60/min, Node store | Task 9 (`checkBffRateLimit`) |
| Fixture parity gate | Task 10 + 13 |
| activityDetail strips documents **and** brief; documentsWithheld | Task 2–3 |
| Vault body server-side only | Task 10–12 |
| CF Function stays; accent out of scope | Global constraints + Task 11 note |
| One PR | Global constraints |
| brief-at-labels → label/trace without themes (no briefWithheld) | Task 2 decision |

**Placeholder scan:** Rate-limit store, snippet budget, brief-withheld shape, and digichat-ui brief kind name are all locked above — no TBD/TODO left for implementers.

**Type consistency:** `brief` kind name, `ActivityBrief`, `MAX_SNIPPET_CHARS`, digivault backend fields, and `createDigivaultStreamResponse` opts are named consistently across tasks.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-05-digichat-phase2-unification.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. **REQUIRED SUB-SKILL:** `superpowers:subagent-driven-development`.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
