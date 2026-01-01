import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  BYOK_PROVIDER_LIST,
  byokKeyPrefixError,
  byokRequiresModel,
} from "./byok-providers";
import { OPENAPI_SERVICE_IDS } from "./openapi";

const repoRoot = resolve(__dirname, "../../..");

describe("byok catalog parity with config/byok-providers.json", () => {
  const json = JSON.parse(
    readFileSync(resolve(repoRoot, "config/byok-providers.json"), "utf8"),
  ) as { id: string; keyPrefix: string; requiresModel: boolean }[];

  it("covers exactly the configured provider ids in order", () => {
    expect([...BYOK_PROVIDER_LIST]).toEqual(json.map((e) => e.id));
  });

  it("agrees on requiresModel and keyPrefix per provider", () => {
    for (const entry of json) {
      expect(byokRequiresModel(entry.id)).toBe(entry.requiresModel);
      // A key built from the JSON prefix must validate clean.
      expect(byokKeyPrefixError(`${entry.keyPrefix}test`, entry.id as never)).toBeNull();
    }
  });
});

describe("openapi registry parity with docs/openapi", () => {
  it("lists every committed OpenAPI JSON (except README)", () => {
    const onDisk = readdirSync(resolve(repoRoot, "docs/openapi"))
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.replace(/\.json$/, ""))
      .sort();
    expect([...OPENAPI_SERVICE_IDS].sort()).toEqual(onDisk);
  });
});
