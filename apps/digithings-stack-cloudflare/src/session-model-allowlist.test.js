import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { SESSION_MODEL_ALLOWLIST_DEFAULT } from "./session-model-allowlist";

/**
 * Pins the stack's default session-model allowlist to the model table the
 * digichat deployment publishes (`apps/digichat/config/digichat-deploy-models.json`).
 *
 * The two lists are the same contract seen from both ends: the published table
 * is what the OCC picker offers, the allowlist is what digigraph will actually
 * bind for that session. When they drift, the failure is silent in both
 * directions — a published model outside the allowlist is replaced by the house
 * default without an error, and an allowlisted model that is not published can
 * never be picked at all. This is the "one definition, two copies" trap the
 * deploy table was extracted to avoid (#5029), so the invariant is pinned here.
 *
 * Deliberately plain `.js`, not `.ts`: `tsconfig.json` scopes `types` to
 * `@cloudflare/workers-types` only (a Workers project, no Node globals), so
 * `node:fs`/`node:path`/`node:url` have no ambient declarations here.
 * `tsconfig.json`'s `include` only matches TypeScript sources, so this file is
 * invisible to `tsc --noEmit`; vitest still runs it via the `.test.{ts,js}` glob
 * in `vitest.config.ts`.
 */

const here = dirname(fileURLToPath(import.meta.url));

const deployModels = JSON.parse(
  readFileSync(resolve(here, "../../digichat/config/digichat-deploy-models.json"), "utf-8"),
);

const allowlist = SESSION_MODEL_ALLOWLIST_DEFAULT.split(",").map((slug) => slug.trim()).filter(Boolean);

describe("session model allowlist", () => {
  it("allows exactly the published, price-capped list", () => {
    expect(new Set(allowlist).size).toBe(allowlist.length);
    expect([...allowlist].sort()).toEqual([...deployModels.sessionAllowlist].sort());
    expect([...allowlist].sort()).toEqual([...deployModels.available].sort());
  });

  it("matches the wrangler.toml value it mirrors", () => {
    const toml = readFileSync(resolve(here, "../wrangler.toml"), "utf-8");
    const line = toml.split("\n").find((row) => row.startsWith("DIGI_SESSION_MODEL_ALLOWLIST"));
    const value = line?.split('"')[1] ?? "";
    expect(value.split(",").sort()).toEqual([...allowlist].sort());
  });

  it("allows the published default model", () => {
    expect(allowlist).toContain(deployModels.default);
  });
});
