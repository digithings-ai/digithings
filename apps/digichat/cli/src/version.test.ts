import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { cliVersion } from "./version.js";

describe("cliVersion", () => {
  it("reports the version in package.json", () => {
    const pkg = JSON.parse(
      readFileSync(new URL("../package.json", import.meta.url), "utf8"),
    ) as { version: string };
    expect(cliVersion()).toBe(pkg.version);
    expect(cliVersion()).toMatch(/^\d+\.\d+\.\d+/);
  });
});
