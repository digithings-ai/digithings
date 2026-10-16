"use client";

import { useEffect, useState } from "react";
import type { RepoModuleRelease } from "@digithings/ui";

/**
 * The per-module release rail's live layer (round 5, #4429).
 *
 * The owner's note: "we could use this one for the release version, the
 * releases for every module as well ... show the latest version, some call-out
 * features from each, but it should be live, it should be live connected live
 * to the latest releases as well."
 *
 * So this hook reads the repo's real releases from the public GitHub REST API,
 * groups them by the product prefix in the tag (`digichat-v2.3.1` is digichat),
 * and reduces each product to its newest release. The committed list the caller
 * passes in is the first paint and the fallback, and it is also the *shape* of
 * the answer: the rail is one card per module, in graph order, so a product the
 * app does not know about is ignored rather than appended.
 *
 * WHY MOST MODULES HAVE NO RELEASE. Release-please only cuts releases for
 * digichat and digiskills today, so a rail built purely from GitHub would show
 * two modules and silently drop the other eight. Every other module falls back
 * to the version it declares for itself — the generated `moduleVersion` data
 * already in `MODULE_RELEASES`. A module with no GitHub release renders its
 * declared version with no feature line and no date; nothing is invented to
 * fill the gap.
 *
 * WHY IT DEGRADES QUIETLY. The site is `output: "export"`, so no fetch may run
 * during render. The read lives in an effect, the committed data is what the
 * static export prerenders, and any failure — rate limit (unauthenticated
 * GitHub allows 60 requests/hour per IP), network, or a malformed payload —
 * keeps that committed data. The band is never blank and never throws.
 *
 * NO SUPABASE, NO NEW ORIGIN. `https://api.github.com` is already in the app's
 * CSP `connect-src` (public/_headers, lib/security-headers.mjs); this adds one
 * public GET and no second service.
 */

const RELEASES_URL =
  "https://api.github.com/repos/digithings-ai/digithings/releases?per_page=100";

/** Past this, the rail settles on the declared versions instead of hanging. */
const REQUEST_TIMEOUT_MS = 8_000;

/** A release body's first bullet, cut to a card-sized line. */
const MAX_TITLE = 140;

/** One row of the GitHub `/releases` payload — only the fields this reads. */
export interface GitHubReleaseRow {
  tag_name?: unknown;
  name?: unknown;
  body?: unknown;
  html_url?: unknown;
  published_at?: unknown;
  created_at?: unknown;
  draft?: unknown;
}

/**
 * `digichat-v2.3.1` → `{ name: "digichat", version: "2.3.1" }`. Returns null for
 * a tag that is not `product-vX.Y.Z`, so a stray tag is skipped rather than
 * rendered as a module named after a date or a hash.
 */
export function moduleFromTag(tag: string): { name: string; version: string } | null {
  const match = /^([a-z][a-z0-9]*)-v(.+)$/.exec(tag.trim());
  if (!match) return null;
  return { name: match[1], version: match[2] };
}

/**
 * The call-out line for a release, taken from the release body: the first
 * bullet when release-please generated one, else the first prose line (a
 * hand-written body). Markdown is stripped — links, the `**scope:**` prefix and
 * the trailing PR/commit refs — so a card shows a sentence, not changelog
 * syntax. Undefined when the body has no usable line; nothing is invented.
 */
export function featureFromBody(body: unknown): string | undefined {
  if (typeof body !== "string" || !body.trim()) return undefined;
  const lines = body.split("\n");
  const bullet = lines.find((line) => /^\s*[-*]\s+\S/.test(line));
  const prose = lines.find((line) => {
    const trimmed = line.trim();
    return trimmed !== "" && !trimmed.startsWith("#") && !/^\s*[-*]\s/.test(line);
  });
  const source = bullet ?? prose;
  if (!source) return undefined;
  return cleanFeature(source) || undefined;
}

function cleanFeature(line: string): string {
  let text = line.trim();
  text = text.replace(/^\s*[-*]\s+/, "");
  text = text.replace(/^\*\*[^*]+\*\*\s*:?\s*/, "");
  text = text.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");
  text = text.replace(/\((?:#[0-9]+|[0-9a-f]{7,})\)/gi, "");
  text = text.replace(/\*\*/g, "").replace(/[*`]/g, "");
  text = text.replace(/\s+/g, " ").trim();
  // Removing a trailing `(#4460)` leaves a space before the colon it followed.
  text = text.replace(/\s+([:;,.!?])/g, "$1");
  text = text.replace(/[.;,]+$/, "").trim();
  if (text.length <= MAX_TITLE) return text;
  const cut = text.slice(0, MAX_TITLE);
  const at = cut.lastIndexOf(" ");
  return `${(at > 40 ? cut.slice(0, at) : cut).trimEnd()}…`;
}

/**
 * Fold the GitHub payload into one release per product, newest first within a
 * product. Drafts and unparseable tags are dropped; a row with no publish stamp
 * is ordered by its creation stamp, and one with neither is treated as oldest.
 */
export function releasesToModuleReleases(payload: unknown): RepoModuleRelease[] {
  if (!Array.isArray(payload)) return [];
  const newest = new Map<string, { release: RepoModuleRelease; at: string }>();

  for (const raw of payload) {
    if (!raw || typeof raw !== "object") continue;
    const row = raw as GitHubReleaseRow;
    if (row.draft === true) continue;
    const tag = typeof row.tag_name === "string" ? row.tag_name.trim() : "";
    if (!tag) continue;
    const parsed = moduleFromTag(tag);
    if (!parsed) continue;

    const at = stampOf(row.published_at) ?? stampOf(row.created_at) ?? "";
    const previous = newest.get(parsed.name);
    if (previous && previous.at >= at) continue;

    const release: RepoModuleRelease = { name: parsed.name, version: parsed.version };
    const url = typeof row.html_url === "string" ? row.html_url : "";
    if (url.startsWith("https://github.com/")) release.url = url;
    const date = at ? at.slice(0, 10) : "";
    if (date) release.date = date;
    const title = featureFromBody(row.body);
    if (title) release.title = title;
    newest.set(parsed.name, { release, at });
  }

  return [...newest.values()].map((entry) => entry.release);
}

function stampOf(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/**
 * Overlay the live releases on the committed list: the fallback decides which
 * modules appear and in what order, and a live release replaces its module's
 * declared entry wholesale. A module with no live release keeps its declared
 * version, untouched and unadorned.
 */
export function mergeModuleReleases(
  fallback: readonly RepoModuleRelease[],
  live: readonly RepoModuleRelease[],
): RepoModuleRelease[] {
  const byName = new Map(live.map((release) => [release.name, release]));
  return fallback.map((seed) => byName.get(seed.name) ?? seed);
}

/**
 * Read the repo's releases. Throws on a non-2xx (rate limit included) or a
 * malformed payload so the caller keeps its committed list; a `null` body
 * parses to an empty list, which the caller also treats as "keep the fallback".
 */
export async function fetchModuleReleases(signal?: AbortSignal): Promise<RepoModuleRelease[]> {
  const controller = signal ? null : new AbortController();
  const effective = signal ?? controller!.signal;
  const response = await fetch(RELEASES_URL, {
    signal: effective,
    headers: { Accept: "application/vnd.github+json" },
  });
  if (!response.ok) throw new Error(`releases responded ${response.status}`);
  return releasesToModuleReleases((await response.json()) as unknown);
}

/**
 * The rail's client hook. Returns the committed list until a live read lands,
 * then the merged list — and the committed list again on any failure. Mount-only
 * on purpose: the committed data is the SSR contract and the read is a one-shot
 * enhance, exactly as `RepoActivity`'s own live refresh works.
 */
export function useModuleReleases(fallback: readonly RepoModuleRelease[]): RepoModuleRelease[] {
  const [releases, setReleases] = useState<RepoModuleRelease[]>(() => [...fallback]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    let cancelled = false;

    (async () => {
      try {
        const live = await fetchModuleReleases(controller.signal);
        if (!cancelled && live.length) setReleases(mergeModuleReleases(fallback, live));
      } catch {
        // Decoration, not a dependency: keep the declared versions, say nothing.
      } finally {
        clearTimeout(timer);
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return releases;
}
