import { edges, modules, type CopyCommandSample, type OdometerStat, type StackItem, type TermLine } from "@digithings/ui";
import { REPO_CLONE } from "@/lib/repoActivity";
import {
  BYOK_KEYS_STORED,
  COMPOSE_DEFAULT,
  COMPOSE_SERVICES,
  COUNTED_AT,
  ROADMAP_MODULES,
  SEARCH_BACKENDS,
  SHIPPING_MODULES,
} from "@/lib/siteCounts";

/**
 * The one content source for every home-page variant (exploration, 2026-09-21).
 *
 * Seven compositions share this file so they cannot drift apart, and — the
 * point of the exercise — so none of them can quietly invent a number. Every
 * figure here comes from `lib/siteCounts.ts` (each with the command that
 * produced it) or from the shared module registry in `@digithings/ui`. When a
 * variant wants something that is not in here, that is the signal to check
 * whether the thing is real before adding it.
 *
 * This directory is a Next private folder (`_variants`), so nothing in it is
 * routed or exported.
 */

export const CLAIM = "AI infrastructure, in a glass box you own.";

export const LEDE =
  "Nine modules you run on your own hosts, against your own provider keys, with every hop of "
  + "every run readable afterwards. Compose them, or take one and leave the rest.";

/** The three channels the repository README documents. No `curl | sh` exists. */
export const INSTALL: CopyCommandSample[] = [
  {
    label: "docker",
    protocol: "git clone",
    code: `${REPO_CLONE} && cd digithings && make up`,
  },
  {
    label: "local",
    protocol: "git clone",
    code: `${REPO_CLONE} && cd digithings && make stack-local`,
  },
  {
    label: "ghcr",
    protocol: "git clone",
    code: `${REPO_CLONE} && cd digithings && make pull-ghcr && make up-ghcr`,
  },
];

export const METRICS: OdometerStat[] = [
  { value: String(SHIPPING_MODULES), label: "modules shipping" },
  { value: String(COMPOSE_SERVICES), label: "compose services" },
  { value: String(SEARCH_BACKENDS), label: "vector backends" },
  { value: String(BYOK_KEYS_STORED), label: "keys stored" },
];

export const COUNTS = {
  shipping: SHIPPING_MODULES,
  roadmap: ROADMAP_MODULES,
  compose: COMPOSE_SERVICES,
  composeDefault: COMPOSE_DEFAULT,
  backends: SEARCH_BACKENDS,
  keysStored: BYOK_KEYS_STORED,
  countedAt: COUNTED_AT,
} as const;

/** Bento spans by tier. Order is load-bearing for CSS Grid auto-placement. */
export type Span = "hero" | "wide" | "tall" | "unit";

export const BENTO: { id: string; span: Span }[] = [
  { id: "digigraph", span: "hero" },
  { id: "digichat", span: "tall" },
  { id: "digisearch", span: "unit" },
  { id: "digikey", span: "unit" },
  { id: "digiquant", span: "wide" },
  { id: "digismith", span: "unit" },
  { id: "digiclaw", span: "unit" },
  { id: "digibase", span: "unit" },
  { id: "digivault", span: "unit" },
  { id: "digistore", span: "unit" },
  { id: "digilink", span: "unit" },
];

export type ModuleRow = {
  id: string;
  name: string;
  tier: string;
  role: string;
  /** The role's tail after the first ` · ` — the grid cell's short line. */
  roleShort: string;
  tagline: string;
  emblem: string;
  dockerCmd: string | null;
  stack: StackItem[];
  /** How many registry edges touch this module — a real, derived number. */
  deps: number;
};

/** All 11 modules, straight from the shared registry. */
export const MODULE_ROWS: ModuleRow[] = modules.map((m) => ({
  id: m.id,
  name: m.name,
  tier: m.tier,
  role: m.role,
  // The registry role is "Category · detail"; a 2-column cell has room for the
  // detail half only, which is the half that says what the module is.
  roleShort: m.role.includes("·") ? m.role.split("·").slice(1).join("·").trim() : m.role,
  tagline: m.tagline,
  emblem: m.emblem,
  dockerCmd: m.dockerCmd,
  stack: m.stack,
  deps: edges.filter((e) => e.a === m.id || e.b === m.id).length,
}));

export const SHIPPING_ROWS = MODULE_ROWS.filter((m) => m.tier !== "roadmap");
export const ROADMAP_ROWS = MODULE_ROWS.filter((m) => m.tier === "roadmap");

/**
 * The request path, for the dashboard-informed variant. Deliberately carries no
 * durations or token counts: nothing in this repository measures that per hop,
 * so a plausible-looking "2.41s" beside each stage would be an invention.
 */
export const REQUEST_PATH: { label: string; detail: string }[] = [
  { label: "edge", detail: "the call arrives with an X-Request-ID, or is given one" },
  { label: "digigraph", detail: "the supervisor routes to the module that owns the work" },
  { label: "subgraph", detail: "research, portfolio, or a typed tool call runs inside the graph" },
  { label: "module", detail: "digisearch, digiquant, digivault — answered by the owning service" },
  { label: "disk", detail: "one redacted JSONL line is appended to the audit trail you own" },
];

/**
 * The documented quick start, transcribed from README.md §"Quick start" and
 * §"Smoke test". Deliberately commands and documented facts only — no captured
 * or imagined command output. A terminal that shows confident output we never
 * ran would be the exact kind of invention this site's rules forbid; the frame
 * that renders this is labelled "README.md · quick start" so it reads as the
 * documented sequence rather than a transcript.
 */
export const QUICKSTART: TermLine[] = [
  { kind: "cmd", text: "cp .env.example .env" },
  { kind: "cmd", text: "make up" },
  { kind: "gap" },
  { kind: "out", text: "# digigraph :8000 · digichat UI :3005 (make up-digichat)" },
  { kind: "out", text: "# no docker: make stack-local → 8000–8003, litellm :4000" },
  { kind: "gap" },
  { kind: "cmd", text: "curl -s -X POST http://127.0.0.1:8000/workflow \\" },
  { kind: "cmd", text: '  -H "Content-Type: application/json" \\' },
  { kind: "cmd", text: '  -d \'{"query": "..."}\'' },
];
