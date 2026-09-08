/**
 * Activity → canon projection (#1418 gap 6).
 *
 * `DigiChatActivity` is the wire vocabulary every backend provider emits (see
 * digichat's `lib/chat-activity.ts`); the shared chat family in
 * `@digithings/web` is the *rendering* vocabulary — collapsible `ChatToolCall`
 * rows, a `ChatThinking` disclosure, `ChatWidgetFrame` cards. The two do not
 * line up field-for-field, so this module is the boundary adapter between
 * them: one pure function, no JSX, no DOM. Session UI in digichat 2.0 reads
 * `source-*` parts directly; these helpers remain for export / legacy hydrate.
 *
 * Keeping the projection separate from the component is what makes the mapping
 * testable in a plain node environment (no jsdom in either consumer's vitest
 * setup) — and it is the seam to extend when the protocol grows a field, so
 * neither the shared primitives nor the renderer has to fork.
 *
 * Fidelity notes — where the wire model carries less than the canon can show:
 *
 *  - **No timings.** `ActivitySpan` has no duration field, so nothing can fill
 *    `ChatToolCall`'s `duration` slot with real milliseconds. It is the head
 *    row's right-aligned mono meta slot, so we spend it on the outcome count
 *    (`3 notes` / `no hits`) — the fact a reader actually wants folded, and
 *    the only way a collapsed result row stays honest about whether the search
 *    found anything.
 *  - **`status` rows have already lost their structure.** By the time a
 *    withheld-documents or failed-search outcome reaches here it is prose
 *    (`Found results for "x".`), with the tool name and query dissolved into
 *    the string upstream. Parsing them back out of prose would be guesswork,
 *    so these render as canon system asides rather than as fake tool rows.
 *  - **Reasoning arrives as one blob**, not pre-segmented steps, so it maps to
 *    `ChatThinking`'s `children` disclosure rather than its railed `steps`
 *    list. See `ChatThinking`'s own docstring, which prescribes exactly this.
 */
import type { ChatToolCallStatus } from "@digithings/web";
import type { DigiChatActivity, VaultHitSummary } from "./types";

/**
 * Ephemeral Foundry ack labels — never chain rows. The session uses a bare
 * flash caret for progress; these would duplicate it and linger after settle.
 */
export const WORKING_LABEL = "Working…";

/** Activities that belong in the tool/trace chain (excludes ephemeral Working…). */
export function chainActivities(
  activities: readonly DigiChatActivity[],
): DigiChatActivity[] {
  return activities.filter(
    (a) => !(a.kind === "trace" && a.label === WORKING_LABEL),
  );
}

/** Path only when it adds information — Foundry search hits set both to the
 *  same chunk id (`page__docs___chunk0`), which was rendering twice. */
export function distinctHitPath(title: string, path: string): string | null {
  return path && path !== title ? path : null;
}

/**
 * One rendered row of the agent chain. Each variant names the shared primitive
 * it becomes, and carries only what that primitive's props need.
 */
export type CanonActivityRow =
  | {
      /** → <ChatToolCall> */
      kind: "tool";
      key: string;
      /** Head name, rendered in the accent. */
      name: string;
      /** Head `(args)` — the query, when the provider sent one. */
      args?: string;
      status: ChatToolCallStatus;
      /** Right-aligned head meta — an outcome count, not a timing (see above). */
      meta?: string;
      /** Retrieved documents, rendered as the fold-out body of this tool row. */
      sources?: VaultHitSummary[];
      /**
       * Running rows carry a body line so the head is expandable (caret).
       * Locate tools use "Searching…"; other in-flight tools use "Working…".
       */
      lines?: string[];
      /** Start expanded when a body is attached. */
      defaultOpen?: boolean;
    }
  | {
      /** → <ChatThinking> */
      kind: "thinking";
      key: string;
      label: string;
      text: string;
    }
  | {
      /** → <ChatWidgetFrame variant="card"> */
      kind: "brief";
      key: string;
      themes: { label: string; summary: string }[];
      questions?: string[];
    }
  | {
      /** → <ChatMessage role="system"> — a `·` aside. */
      kind: "aside";
      key: string;
      message: string;
    };

/** `3 notes` / `1 note` / `no hits` — the folded outcome read. */
export function outcomeMeta(count: number): string {
  if (count <= 0) return "no hits";
  return `${count} note${count === 1 ? "" : "s"}`;
}

const TOOL_LABELS: Record<string, string> = {
  digisearch: "Search the knowledge base",
  azure_ai_search: "Search the knowledge base",
  rag_sources: "Search the knowledge base",
  digivault: "Vault",
  digivault_search_notes: "Vault",
  digivault_get_note: "Load vault note",
  web_search: "Web search (External)",
};

/** Wire ids whose in-flight fold should read "Searching…", not "Working…". */
const LOCATE_TOOL_NAMES = new Set([
  "digisearch",
  "azure_ai_search",
  "rag_sources",
  "digivault",
  "digivault_search_notes",
  "web_search",
]);

/** Human labels for the head only — identity keys still use the wire tool id. */
export function toolDisplayName(name: string): string {
  return TOOL_LABELS[name] ?? name;
}

/** In-flight body so the head stays a disclosure; locate tools keep Searching…. */
function inFlightToolLines(toolName: string): string[] {
  return LOCATE_TOOL_NAMES.has(toolName) ? ["Searching…"] : [WORKING_LABEL];
}

const QUERY_DISPLAY_MAX = 80;

/** Omit a query that already appeared on the previous row; truncate long ones. */
export function displayArgs(
  query: string | undefined,
  previousQuery: string | undefined,
): string | undefined {
  const q = query?.trim();
  if (!q) return undefined;
  if (previousQuery?.trim() === q) return undefined;
  if (q.length <= QUERY_DISPLAY_MAX) return q;
  return `${q.slice(0, QUERY_DISPLAY_MAX - 1).trimEnd()}…`;
}

/** Strip markdown chrome so a snippet reads as a sentence, not a wall. */
export function readableSnippet(raw: string, max = 220): string {
  let s = raw
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/!\[[^\]]*]\([^)]*\)/g, " ")
    .replace(/\[([^\]]*)]\([^)]*\)/g, "$1")
    .replace(/[#*_`>~]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!s) return "";
  if (s.length <= max) return s;
  const cut = s.slice(0, max);
  const lastStop = Math.max(
    cut.lastIndexOf(". "),
    cut.lastIndexOf("? "),
    cut.lastIndexOf("! "),
  );
  const end =
    lastStop > max * 0.45 ? cut.slice(0, lastStop + 1) : cut.replace(/\s+\S*$/, "");
  return `${end.trimEnd()}…`;
}

function previousQueryAt(
  activities: readonly DigiChatActivity[],
  i: number,
): string | undefined {
  const prev = activities[i - 1];
  if (!prev || !("query" in prev)) return undefined;
  return prev.query;
}

function hitsForDisplay(hits: VaultHitSummary[] | undefined): VaultHitSummary[] | undefined {
  if (!hits?.length) return undefined;
  return hits.map((hit) =>
    hit.snippet ? { ...hit, snippet: readableSnippet(hit.snippet) } : hit,
  );
}

/**
 * Projects the wire activities onto canon rows, in order.
 *
 * Keyed by IDENTITY, not position. Position is not stable: `toDigiChatActivity`
 * appends the reasoning row last, after every tool row, so its index climbs each
 * time a tool arrives; it also rewrites a row in place from `tool_call` to
 * `tool_result` (kind is part of any composite key), and its final filter drops
 * orphaned placeholders, shifting everything after them. Since `ChatThinking`
 * and `ChatToolCall` are uncontrolled, a changed key is an unmount — so an
 * index key collapsed a disclosure the reader had opened, mid-stream, and
 * removed its text from the DOM.
 *
 * Reasoning is a singleton per turn, so it keys as itself. Tool rows key on
 * name+query, which is the identity the producer already groups by internally.
 * A trailing index still disambiguates genuine duplicates.
 */
/**
 * A key that survives the row moving. `reasoning` is one per turn so it needs no
 * suffix; tool rows carry name+query (the producer's own grouping key) and a
 * trailing index only to separate true duplicates.
 */
function identityKey(activity: DigiChatActivity, i: number): string {
  switch (activity.kind) {
    case "reasoning":
      return "reasoning";
    case "tool_call":
    case "tool_result":
      return `tool:${activity.name}|${"query" in activity ? (activity.query ?? "") : ""}`;
    default:
      return `${activity.kind}-${i}`;
  }
}

export function toCanonRows(activities: readonly DigiChatActivity[]): CanonActivityRow[] {
  return activities.map((activity, i): CanonActivityRow => {
    const key = identityKey(activity, i);
    const args =
      "query" in activity ? displayArgs(activity.query, previousQueryAt(activities, i)) : undefined;
    switch (activity.kind) {
      case "tool_call":
        return {
          kind: "tool",
          key,
          name: toolDisplayName(activity.name),
          ...(args ? { args } : {}),
          status: "running",
          lines: inFlightToolLines(activity.name),
        };

      case "tool_result":
        return {
          kind: "tool",
          key,
          name: toolDisplayName(activity.name),
          ...(args ? { args } : {}),
          status: "ok",
          meta: outcomeMeta(activity.count),
          ...(activity.hits.length ? { sources: hitsForDisplay(activity.hits) } : {}),
        };

      case "trace":
        // An opaque upstream step. It has a label but no arguments and no
        // output, so it rebuilds as a bodyless tool row — the canon's own
        // read for "a step that ran".
        return {
          kind: "tool",
          key,
          name: activity.label,
          status: activity.done ? "ok" : "running",
        };

      case "reasoning":
        return { kind: "thinking", key, label: "reasoning", text: activity.text };

      case "brief":
        return {
          kind: "brief",
          key,
          themes: activity.themes,
          ...(activity.questions?.length ? { questions: activity.questions } : {}),
        };

      case "status":
        return { kind: "aside", key, message: activity.message };

      default: {
        const _exhaustive: never = activity;
        void _exhaustive;
        return { kind: "aside", key, message: "" };
      }
    }
  });
}

/**
 * The step to show in the waiting caret: what the agent is doing *right now*,
 * or nothing.
 *
 * The caret used to cycle a hard-coded script — "thinking", "routing through
 * digigraph", "gathering context", "composing the answer" — on a ~10s loop
 * regardless of what was happening. It read as a placeholder because it was
 * one: none of those words were tied to any real step, and two of them named
 * a backend this transcript may not even be talking to.
 *
 * So the label comes from the stream or there is no label. `undefined` means
 * the caller shows a bare blinking cursor — an honest "something is happening"
 * beats a confident sentence about the wrong thing.
 *
 * Scans from the end because the newest unfinished step is the current one.
 * A tool row is "unfinished" until a tool_result for the same name arrives;
 * matching on name alone (not name+query) is deliberate, since a call's query
 * is often still empty while it is in flight — that is exactly the case this
 * has to cover.
 */
export function liveActivityLabel(activities: DigiChatActivity[]): string | undefined {
  const settledTools = new Set<string>();
  for (let i = activities.length - 1; i >= 0; i -= 1) {
    const activity = activities[i];
    switch (activity.kind) {
      case "tool_result":
        settledTools.add(activity.name);
        break;
      case "tool_call": {
        if (settledTools.has(activity.name)) break;
        const query = activity.query?.trim();
        return query ? `Searching for "${query}"` : "Searching…";
      }
      case "trace":
        if (!activity.done) return activity.label;
        break;
      default:
        break;
    }
  }
  return undefined;
}

/**
 * Deduped hit list across settled searches on a turn. Kept for callers that
 * want a flat view; the session renders hits on each tool row instead.
 */
export function citationHits(activities: readonly DigiChatActivity[]): VaultHitSummary[] {
  const out: VaultHitSummary[] = [];
  const byPath = new Map<string, number>();
  for (const activity of activities) {
    if (activity.kind !== "tool_result") continue;
    for (const hit of activity.hits) {
      const idx = byPath.get(hit.path);
      if (idx === undefined) {
        byPath.set(hit.path, out.length);
        out.push(hit);
        continue;
      }
      if (!out[idx].body && hit.body) {
        out[idx] = hit;
      }
    }
  }
  return out;
}

/** Foundry inline markers — `【9:0†source】` — stream as raw answer text.
 *  Strip so the prose stays human-readable; the chunks already sit on the
 *  search tool row that produced them. */
export function stripFoundryCitationMarkers(text: string): string {
  return text
    .replace(/\u3010[\d:]+\u2020source\u3011/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/ {2,}/g, " ")
    .trimEnd();
}
