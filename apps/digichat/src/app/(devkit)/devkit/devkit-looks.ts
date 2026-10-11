/**
 * Devkit look catalog + preview mode switch (DIG-2962).
 *
 * Pure + client-safe (no node imports, no fs). Two jobs:
 *
 * 1. LOOKS — the nine shipped YAML configs collapse to the looks a reviewer
 *    actually compares: the default client looks, occ, datatap, digichat and
 *    the pop-up banner. Nothing is deleted and nothing disappears: every entry
 *    lands in exactly one look and each look keeps every variant id, so the
 *    selector can still reach a file the brief did not name (the CLI look).
 *    Deleting the twins instead would break other seats' suites —
 *    `deploy-config/schema.test.ts` walks the examples dir, `mcp-servers.test.ts`
 *    reads `dashboard-modal.yaml`, `embed-chat-tenant.test.ts` reads
 *    `digithings-ai-embed.yaml` + `occ-embed.yaml`.
 *
 * 2. MODES — every look renders in three presentation modes. The chrome
 *    schema has four values (`app | embed | modal | sidebar`); the brief names
 *    three, which map onto existing values: fullscreen = `app`,
 *    pop-up = `modal`, embedded = `embed`. `sidebar` stays reachable by
 *    editing the config text, which is where the other chrome values live.
 */

import type { ChromeMode } from "@/lib/deploy-config/schema";

export type DevkitLookId =
  | "client"
  | "occ"
  | "datatap"
  | "digichat"
  | "banner"
  | "cli"
  | "skins";

export interface DevkitLook {
  id: DevkitLookId;
  /** Operator-facing label, brand lowercased throughout. */
  label: string;
  /** The chrome mode this look ships with, as authored. */
  authoredMode: ChromeMode;
}

/**
 * Order is the reviewer's order, not alphabetical: the default client looks
 * first, then the product hosts, then the pop-up banner, then the CLI.
 */
export const DEVKIT_LOOKS: readonly DevkitLook[] = [
  { id: "client", label: "default client looks", authoredMode: "app" },
  { id: "occ", label: "occ", authoredMode: "embed" },
  { id: "datatap", label: "datatap", authoredMode: "embed" },
  { id: "digichat", label: "digichat", authoredMode: "embed" },
  { id: "banner", label: "pop-up banner", authoredMode: "modal" },
  { id: "cli", label: "digichat cli", authoredMode: "app" },
  { id: "skins", label: "thread skins", authoredMode: "app" },
];

export type DevkitModeId = "fullscreen" | "popup" | "embedded";

export interface DevkitMode {
  id: DevkitModeId;
  label: string;
  chromeMode: ChromeMode;
}

/**
 * The three modes the brief names, in the order the matrix reads.
 * Each is a chrome-schema value, so switching a mode exercises real config.
 */
export const DEVKIT_MODES: readonly DevkitMode[] = [
  { id: "fullscreen", label: "fullscreen", chromeMode: "app" },
  { id: "popup", label: "pop-up", chromeMode: "modal" },
  { id: "embedded", label: "embedded", chromeMode: "embed" },
];

export function devkitModeForChrome(mode: ChromeMode | undefined): DevkitModeId {
  const hit = DEVKIT_MODES.find((m) => m.chromeMode === mode);
  return hit ? hit.id : "embedded";
}

/**
 * Return a copy of `deployment` with `chrome.mode` forced to `mode`.
 * Clones rather than mutates: the draft text is the source of truth and the
 * preview must not write back into it, or the mode switch would dirty a draft
 * the operator never edited.
 */
export function withChromeMode<T extends { chrome?: { mode?: string } }>(
  deployment: T,
  mode: ChromeMode,
): T {
  const next = structuredClone(deployment) as T & { chrome: { mode: ChromeMode } };
  next.chrome = { ...(next.chrome ?? {}), mode };
  return next;
}

export interface LookCandidate {
  id: string;
  slug: string;
  chromeMode: ChromeMode | undefined;
}

export interface DevkitLookGroup {
  id: DevkitLookId;
  label: string;
  /** Entry ids in presentation order; the first is the group's representative. */
  variantIds: string[];
}

/**
 * Classify one entry. Slug wins over chrome mode so a modal deployment that
 * is not the dashboard banner does not silently become the banner; the modal
 * arm is the fallback that gives `dashboard-modal.yaml` its own look.
 */
export function lookForEntry(entry: LookCandidate): DevkitLookId {
  const slug = (entry.slug ?? "").toLowerCase();
  if (slug === "occ" || slug.startsWith("occ-")) return "occ";
  if (slug.startsWith("datatap")) return "datatap";
  if (slug.startsWith("digithings-ai") || slug === "digithat") return "digichat";
  if (slug.startsWith("client-") || slug.startsWith("base-")) return "skins";
  if (slug.startsWith("local-cli")) return "cli";
  if (slug.startsWith("digiquant-dashboard")) return "banner";
  if (slug.startsWith("local-app")) return "client";
  if (entry.chromeMode === "modal") return "banner";
  return "client";
}

/**
 * Group every entry into its look, preserving DEVKIT_LOOKS order and, within a
 * look, the caller's order. `seen` guards a duplicate entry id so two callers
 * feeding the same list cannot double-count a variant.
 */
export function groupEntriesByLook(
  entries: readonly LookCandidate[],
): DevkitLookGroup[] {
  const buckets = new Map<DevkitLookId, string[]>();
  const seen = new Set<string>();
  for (const entry of entries) {
    if (seen.has(entry.id)) continue;
    seen.add(entry.id);
    const look = lookForEntry(entry);
    const list = buckets.get(look);
    if (list) list.push(entry.id);
    else buckets.set(look, [entry.id]);
  }
  return DEVKIT_LOOKS.filter((l) => buckets.has(l.id)).map((l) => ({
    id: l.id,
    label: l.label,
    variantIds: buckets.get(l.id) as string[],
  }));
}
