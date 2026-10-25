import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { DIGITHINGS_ONLY_CORPUS_JSON, composeCorpusMap } from "./tenant-config";

/**
 * The corpus map is two wrangler `[vars]` because one text binding may not
 * exceed 5.1 kB (deploy error 10054, 2026-10-25). `composeCorpusMap` joins them
 * at boot; this gate pins both halves of that promise:
 *
 *  - the merge is LOSSLESS: the composed string is the object the single 5285
 *    byte var used to hold, OCC `researchSystemPrompt` included, byte for byte;
 *  - the merge is FAIL-CLOSED: a broken half cannot widen or empty the map, and
 *    the house entry can never be displaced by the extra half.
 *
 * The expected value is read from the dev-path copy in
 * `infra/digichat-release/compose.profile-a-bundle.override.yml`, which is an
 * independent transcription of the same tenant entry. Comparing against a
 * fixture of our own two halves would be circular and would pass while both
 * halves rotted together.
 *
 * Deliberately plain `.js` for the reason documented in `env-vars-pin.test.js`:
 * `tsconfig.json` scopes `types` to `@cloudflare/workers-types`, so `node:fs`
 * has no ambient declaration in this package, and `tsconfig.json`'s `include`
 * only matches TypeScript sources -- this file is invisible to `tsc --noEmit`.
 */

const HERE = dirname(fileURLToPath(import.meta.url));
const WRANGLER = join(HERE, "..", "wrangler.toml");
const COMPOSE = join(
  HERE,
  "..",
  "..",
  "..",
  "infra",
  "digichat-release",
  "compose.profile-a-bundle.override.yml",
);

/**
 * A TOML basic-string value for one `[vars]` key, or `undefined` when absent.
 *
 * Hand-rolled because this package has no TOML parser and the values are plain
 * one-line JSON strings. A value that is re-wrapped onto a continuation line, or
 * carries an escape this reader does not implement, throws instead of parsing to
 * almost-the-right-answer -- a silently mangled prompt byte is exactly the
 * failure the equality assertion below exists to catch.
 */
function tomlVar(source, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`^${escaped} = "(.*)"$`, "m").exec(source);
  if (!match) return undefined;
  return decodeTomlBasicString(match[1], name);
}

/**
 * Decode a TOML basic string's escapes, refusing any it does not implement.
 *
 * The values here are JSON, so in practice this only ever meets `\\"` (a JSON
 * quote) and `\\\\` (a backslash in a prompt), but the full basic-string set is
 * handled so a future value cannot decode to almost-the-right-answer.
 */
function decodeTomlBasicString(body, name) {
  const singles = { "\\": "\\", '"': '"', n: "\n", t: "\t", r: "\r", b: "\b", f: "\f" };
  return body.replace(/\\(u[0-9a-fA-F]{4}|.)/g, (whole, seq) => {
    if (seq.length === 5) return String.fromCharCode(parseInt(seq.slice(1), 16));
    if (Object.prototype.hasOwnProperty.call(singles, seq)) return singles[seq];
    throw new Error(`${name} uses \\${seq}, an escape this reader does not implement`);
  });
}

/**
 * The stack service's `DIGI_TENANT_CORPUS_MAP` from the compose override.
 *
 * The value is a single-line single-quoted YAML scalar, so the line itself is
 * the blob; an anchor of one is required so a second copy cannot be picked up
 * silently.
 */
function composeCorpusJson() {
  const source = readFileSync(COMPOSE, "utf8");
  const found = [...source.matchAll(/^\s*DIGI_TENANT_CORPUS_MAP: '(.*)'$/gm)].map((m) => m[1]);
  if (found.length !== 1) {
    throw new Error(`expected exactly one DIGI_TENANT_CORPUS_MAP line in the compose override, got ${found.length}`);
  }
  return found[0];
}

const wranglerSource = () => readFileSync(WRANGLER, "utf8");
const primary = () => tomlVar(wranglerSource(), "DIGI_TENANT_CORPUS_MAP");
const extra = () => tomlVar(wranglerSource(), "DIGI_TENANT_CORPUS_MAP_EXTRA");

describe("composeCorpusMap: the split [vars] pair rejoins into the old map", () => {
  it("ships both halves as separate vars, each under Cloudflare's 5.1 kB cap", () => {
    // A zero here would make every assertion below vacuous.
    expect(primary()).toBeTruthy();
    expect(extra()).toBeTruthy();
    expect(primary().length).toBeGreaterThan(0);
    expect(extra().length).toBeGreaterThan(0);
    // 5100 is the limit the deploy reported (5.1 kB); leave the same headroom
    // Cloudflare measures against, not a fudge factor.
    expect(primary().length).toBeLessThan(5100);
    expect(extra().length).toBeLessThan(5100);
  });

  it("puts the house tenant in the unsuffixed var and the rest in the extra one", () => {
    // digigraph reads DIGI_TENANT_CORPUS_MAP by name, so the house entry must
    // stay in it; splitting it the other way would break the deployed reader.
    expect(Object.keys(JSON.parse(primary()))).toEqual(["digithings"]);
    expect(Object.keys(JSON.parse(extra()))).toContain("occ");
    expect(JSON.parse(primary())).not.toHaveProperty("occ");
  });

  it("composes the byte-identical old value, OCC prompt included", () => {
    const composed = composeCorpusMap(primary(), extra());
    const expected = JSON.parse(composeCorpusJson());
    const actual = JSON.parse(composed);

    // Deep equality against the full previous object: any drift in a slug, an
    // index, a vault prefix or one byte of either research prompt fails here.
    expect(actual).toEqual(expected);
    expect(Object.keys(actual)).toEqual(["digithings", "occ"]);
    expect(actual.occ.researchSystemPrompt).toBe(expected.occ.researchSystemPrompt);
    expect(actual.digithings.researchSystemPrompt).toBe(expected.digithings.researchSystemPrompt);

    // Not just the same object: the same SERIALISED value, so a change of key
    // order or of compactness (which would rewrite the container's config blob)
    // is caught too.
    expect(composed).toBe(JSON.stringify(expected));
  });

  it("lets the primary half win a slug collision", () => {
    // A stale extra must never shadow the house entry it does not own.
    const composed = composeCorpusMap(
      '{"digithings":{"digisearchIndex":"house","vaultPathPrefix":"clients/house"}}',
      '{"digithings":{"digisearchIndex":"stale","vaultPathPrefix":"clients/stale"},"occ":{"digisearchIndex":"occ_help"}}',
    );
    const map = JSON.parse(composed);
    expect(map.digithings.digisearchIndex).toBe("house");
    expect(map.digithings.vaultPathPrefix).toBe("clients/house");
    expect(map.occ.digisearchIndex).toBe("occ_help");
  });

  it("keeps the readable half when one half does not parse", () => {
    const brokenPrimary = composeCorpusMap("{not json", '{"occ":{"digisearchIndex":"occ_help"}}');
    expect(JSON.parse(brokenPrimary)).toEqual({ occ: { digisearchIndex: "occ_help" } });

    const brokenExtra = composeCorpusMap('{"digithings":{"digisearchIndex":"digithings_docs"}}', "[]");
    expect(JSON.parse(brokenExtra)).toEqual({ digithings: { digisearchIndex: "digithings_docs" } });
  });

  it("falls back to the first-party tenant when neither half is usable", () => {
    expect(composeCorpusMap("{not json", "{also not json")).toBe(DIGITHINGS_ONLY_CORPUS_JSON);
    expect(JSON.parse(composeCorpusMap("{not json", "{}"))).toEqual({
      digithings: { digisearchIndex: "digithings_docs", vaultPathPrefix: "clients/digithings" },
    });
  });

  it("falls back to the first-party tenant when neither var is set", () => {
    // Never an empty string: an empty map makes every tenant unknown, which the
    // container reads as a refusal rather than as "no overrides".
    expect(composeCorpusMap(undefined, undefined)).toBe(DIGITHINGS_ONLY_CORPUS_JSON);
    expect(composeCorpusMap("", "")).toBe(DIGITHINGS_ONLY_CORPUS_JSON);
    expect(composeCorpusMap()).toBe(DIGITHINGS_ONLY_CORPUS_JSON);
  });

  it("is the unchanged single-var path when only DIGI_TENANT_CORPUS_MAP is set", () => {
    // Back-compat: a deployment that has not taken the second var yet must
    // behave exactly as it did before the split.
    const only = '{"digithings":{"digisearchIndex":"digithings_docs"}}';
    expect(composeCorpusMap(only, undefined)).toBe(only);
  });
});
