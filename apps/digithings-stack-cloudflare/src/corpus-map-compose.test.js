import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";

import { DIGITHINGS_ONLY_CORPUS_JSON, composeCorpusMap } from "./tenant-config";

/**
 * The corpus map is split: the house entry is a wrangler `[vars]` value and every
 * other tenant is the DIGI_TENANT_CORPUS_MAP_PRIVATE Worker secret (client config
 * stays out of this public repo, DIG-3585; the split itself dates from the 5.1 kB
 * binding cap, deploy error 10054). `composeCorpusMap` joins them at boot; this
 * gate pins both halves of that promise:
 *
 *  - the merge is LOSSLESS: the composed string carries the object the single
 *    5285 byte var used to hold, OCC `researchSystemPrompt` included, plus the
 *    house-slug alias (`digithings-ai`, DIG-5638) that every map arm carries;
 *  - the merge is FAIL-CLOSED: a broken half cannot widen or empty the map, the
 *    house entry can never be displaced by the extra half, and an unknown
 *    tenant is never invented.
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
/**
 * Stand-in for the DIGI_TENANT_CORPUS_MAP_PRIVATE Worker secret: every non-house
 * tenant from the independent compose transcription. The secret's real value is
 * not in this repo (DIG-3585), so the test composes against the same shape.
 */
const privateHalf = () => {
  const all = JSON.parse(composeCorpusJson());
  const rest = {};
  for (const [slug, entry] of Object.entries(all)) {
    if (slug !== "digithings") rest[slug] = entry;
  }
  return JSON.stringify(rest);
};

describe("composeCorpusMap: the house var and the private-tenant secret rejoin", () => {
  it("ships only the house tenant in [vars], under Cloudflare's 5.1 kB cap", () => {
    // A zero here would make every assertion below vacuous.
    expect(primary()).toBeTruthy();
    expect(primary().length).toBeGreaterThan(0);
    // 5100 is the limit the deploy reported (5.1 kB).
    expect(primary().length).toBeLessThan(5100);
    // digigraph reads DIGI_TENANT_CORPUS_MAP by name, so the house entry must
    // stay in it -- and nothing else may: other tenants are client config.
    expect(Object.keys(JSON.parse(primary()))).toEqual(["digithings"]);
  });

  it("keeps every non-house tenant out of the public wrangler.toml (DIG-3585)", () => {
    // The old second [vars] half carried a client's routing and research prompt
    // in a public file. It now lives in a Worker secret; neither name may come
    // back as a plain var.
    expect(tomlVar(wranglerSource(), "DIGI_TENANT_CORPUS_MAP_EXTRA")).toBeUndefined();
    expect(tomlVar(wranglerSource(), "DIGI_TENANT_CORPUS_MAP_PRIVATE")).toBeUndefined();
    for (const slug of Object.keys(JSON.parse(privateHalf()))) {
      expect(wranglerSource()).not.toContain(`\\"${slug}\\":{`);
    }
  });

  it("composes the house var and the private secret into the full map plus the alias", () => {
    const composed = composeCorpusMap(primary(), privateHalf());
    const expected = JSON.parse(composeCorpusJson());
    const actual = JSON.parse(composed);

    // The dev-path compose copy names the house tenant `digithings` only, while
    // the live embed slug is `digithings-ai`; composition must carry both keys
    // with the SAME entry, or digivault refuses the live chat with 403.
    const expectedWithAlias = { digithings: expected.digithings, "digithings-ai": expected.digithings };
    for (const [slug, entry] of Object.entries(expected)) {
      if (slug !== "digithings") expectedWithAlias[slug] = entry;
    }

    // Deep equality against the full transcribed object: any drift in a slug,
    // an index, a vault prefix or one byte of the house research prompt fails here.
    expect(actual).toEqual(expectedWithAlias);
    expect(Object.keys(actual).slice(0, 2)).toEqual(["digithings", "digithings-ai"]);
    expect(actual.digithings.digisearchIndex).toBe("digithings_docs");
    expect(actual.digithings.vaultPathPrefix).toBe("clients/digithings");
    expect(actual["digithings-ai"]).toEqual(actual.digithings);
    expect(actual.digithings.researchSystemPrompt).toBe(expected.digithings.researchSystemPrompt);

    // Not just the same object: the same SERIALISED value, so a change of key
    // order or of compactness (which would rewrite the container's config blob)
    // is caught too.
    expect(composed).toBe(JSON.stringify(expectedWithAlias));
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
    // `occ` alone carries no house slug, so no house entry is invented.
    const brokenPrimary = composeCorpusMap("{not json", '{"occ":{"digisearchIndex":"occ_help"}}');
    expect(JSON.parse(brokenPrimary)).toEqual({ occ: { digisearchIndex: "occ_help" } });

    const brokenExtra = composeCorpusMap('{"digithings":{"digisearchIndex":"digithings_docs"}}', "[]");
    expect(JSON.parse(brokenExtra)).toEqual({
      digithings: { digisearchIndex: "digithings_docs" },
      "digithings-ai": { digisearchIndex: "digithings_docs" },
    });
  });

  it("falls back to the first-party tenant under both house slugs", () => {
    expect(composeCorpusMap("{not json", "{also not json")).toBe(DIGITHINGS_ONLY_CORPUS_JSON);
    expect(JSON.parse(composeCorpusMap("{not json", "{}"))).toEqual({
      digithings: { digisearchIndex: "digithings_docs", vaultPathPrefix: "clients/digithings" },
      "digithings-ai": {
        digisearchIndex: "digithings_docs",
        vaultPathPrefix: "clients/digithings",
      },
    });
  });

  it("falls back to the first-party tenant when neither var is set", () => {
    // Never an empty string: an empty map makes every tenant unknown, which the
    // container reads as a refusal rather than as "no overrides".
    expect(composeCorpusMap(undefined, undefined)).toBe(DIGITHINGS_ONLY_CORPUS_JSON);
    expect(composeCorpusMap("", "")).toBe(DIGITHINGS_ONLY_CORPUS_JSON);
    expect(composeCorpusMap()).toBe(DIGITHINGS_ONLY_CORPUS_JSON);
  });

  it("adds only the house alias when only DIGI_TENANT_CORPUS_MAP is set", () => {
    // A deployment whose private secret is not set yet still composes to the
    // house corpus under both slugs (fail closed for every other tenant).
    const only = '{"digithings":{"digisearchIndex":"digithings_docs"}}';
    expect(JSON.parse(composeCorpusMap(only, undefined))).toEqual({
      digithings: { digisearchIndex: "digithings_docs" },
      "digithings-ai": { digisearchIndex: "digithings_docs" },
    });
  });
});

/**
 * The pre-hardening merge, verbatim in behaviour: exact-match house-wins, raw
 * keys. For canonical client slugs the hardened composeCorpusMap must produce
 * the SAME bytes, so today's deployed config does not change.
 */
function legacyCompose(primaryRaw, extraRaw) {
  const parse = (raw) => {
    try {
      const v = JSON.parse(raw);
      if (typeof v !== "object" || v === null || Array.isArray(v)) return undefined;
      const out = {};
      for (const [k, e] of Object.entries(v)) {
        if (typeof e === "object" && e !== null && !Array.isArray(e)) out[k] = e;
      }
      return Object.keys(out).length ? out : undefined;
    } catch {
      return undefined;
    }
  };
  const merged = { ...parse(primaryRaw) };
  for (const [k, e] of Object.entries(parse(extraRaw) ?? {})) if (!(k in merged)) merged[k] = e;
  const house = merged.digithings;
  const out = {};
  for (const [k, e] of Object.entries(merged)) {
    if (k === "digithings" || k === "digithings-ai") {
      if (!("digithings" in out)) {
        out.digithings = house;
        out["digithings-ai"] = house;
      }
      continue;
    }
    out[k] = e;
  }
  return JSON.stringify(out);
}

describe("composeCorpusMap: slug normalisation keeps today's config byte-identical", () => {
  it("matches the pre-hardening output for the real house var, alone and with canonical client slugs", () => {
    const silent = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      expect(composeCorpusMap(primary(), undefined)).toBe(legacyCompose(primary(), "{}"));
      expect(composeCorpusMap(primary(), privateHalf())).toBe(legacyCompose(primary(), privateHalf()));
      const clients = JSON.stringify({
        "tenant-a": { digisearchIndex: "a", webSearchDomains: ["a.example"] },
        "tenant-b": { digisearchIndex: "b", researchSystemPrompt: "p" },
      });
      expect(composeCorpusMap(primary(), clients)).toBe(legacyCompose(primary(), clients));
      expect(silent).not.toHaveBeenCalled();
    } finally {
      silent.mockRestore();
    }
  });

  it("drops private-secret slugs that normalise to the house tenant, keeping the real house entry", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const evil = { digisearchIndex: "stolen", vaultPathPrefix: "clients/other", webSearchDomains: ["x.example"] };
      const extra = JSON.stringify({
        DIGITHINGS: evil,
        " digithings": evil,
        "Digithings-AI": evil,
        "\tdigithings-ai": evil,
        "tenant-a": { digisearchIndex: "a" },
      });
      const out = JSON.parse(composeCorpusMap(primary(), extra));
      const house = JSON.parse(primary()).digithings;
      expect(Object.keys(out)).toEqual(["digithings", "digithings-ai", "tenant-a"]);
      expect(out.digithings).toEqual(house);
      expect(out["digithings-ai"]).toEqual(house);
      expect(warn).toHaveBeenCalled();
    } finally {
      warn.mockRestore();
    }
  });
});
