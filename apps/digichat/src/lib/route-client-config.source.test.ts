import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { DEFAULT_CLIENT_CONFIG } from "./deploy-config";
import { HOUSE_BACKEND_ID } from "./provider-label";
import { toStockChatPrefsConfig } from "./route-client-config";

const here = dirname(fileURLToPath(import.meta.url));
const routeClientConfigSrc = readFileSync(
  join(here, "route-client-config.ts"),
  "utf8",
);

/** The one import the house backend id may come from. */
const houseBackendImport =
  /import\s*\{[^}]*\bHOUSE_BACKEND_ID\b[^}]*\}\s*from\s*["'](?:\.\/|@\/lib\/)provider-label["']/g;

/**
 * The static surfaces that render the chip without a session of their own:
 * the home, the baseline and the devkit. They carry no BYOK state, so they
 * name the house backend - through the shared helper, never through a copy
 * of today's value.
 */
const staticSurfaces = [
  "../app/(digichat)/home-stock-client.tsx",
  "../app/(baseline)/baseline/baseline-client.tsx",
  "../app/(devkit)/devkit/devkit-preview.tsx",
];

/** Code lines only - comments state the rule, they do not implement it. */
function codeLinesOf(source: string): string[] {
  return source
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      return (
        trimmed.length > 0 &&
        !trimmed.startsWith("//") &&
        !trimmed.startsWith("*") &&
        !trimmed.startsWith("/*")
      );
    });
}

describe("the static composer provider chip", () => {
  it("derives the label from the shared house-backend constant, not from a literal", () => {
    // One place wires the label for the static surfaces.
    const labelLines = codeLinesOf(routeClientConfigSrc).filter((line) =>
      /providerLabel\s*:/.test(line),
    );
    expect(labelLines).toHaveLength(1);
    expect(labelLines[0]).toMatch(/providerLabel\s*:\s*HOUSE_BACKEND_ID\b/);
    // No literal backend name: a copy of today's value renders the same
    // label today and drifts the moment the house backend changes.
    expect(labelLines[0]).not.toMatch(/["'`]/);
  });

  it("reads the constant from its one home, with no copy of its own", () => {
    expect(routeClientConfigSrc.match(houseBackendImport)).toHaveLength(1);
    // A local copy of the constant shadows the import and drifts with it.
    expect(routeClientConfigSrc).not.toMatch(
      /(?:const|let|var|function)\s+HOUSE_BACKEND_ID\b/,
    );
  });

  it("leaves the static surfaces without a label of their own", () => {
    for (const surface of staticSurfaces) {
      const lines = codeLinesOf(readFileSync(join(here, surface), "utf8"));
      // A surface that names a backend itself holds a copy of it. The
      // shared helper is the one home of the house backend id.
      expect(
        lines.filter((line) => /providerLabel\s*:/.test(line)),
        surface,
      ).toEqual([]);
    }
  });

  it("names the house backend on the static surfaces", () => {
    expect(toStockChatPrefsConfig(DEFAULT_CLIENT_CONFIG).providerLabel).toBe(
      HOUSE_BACKEND_ID,
    );
  });
});
