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

/**
 * The composer provider chip on the static surfaces (DIG-4879).
 *
 * The home, baseline and devkit surfaces carry no BYOK state of their own -
 * the provider menu they render cannot activate an own key - so they name
 * the house backend (ARCHITECTURE.md, "The composer provider chip names the
 * backend that serves the chat").
 *
 * They have to name it through the shared constant, not through a copy of
 * its current value: a literal renders the same label today and drifts the
 * moment the house backend changes. A render cannot see that difference, so
 * the wiring is pinned from the source here.
 */
describe("the static composer provider chip", () => {
  it("derives the label from the shared house-backend constant, not from a literal", () => {
    expect(routeClientConfigSrc).toMatch(/providerLabel:\s*HOUSE_BACKEND_ID\b/);
    expect(routeClientConfigSrc).not.toMatch(/providerLabel:\s*["'`]/);
    // The constant itself comes from the one home of the house backend id.
    expect(routeClientConfigSrc).toMatch(
      /import\s*\{[^}]*\bHOUSE_BACKEND_ID\b[^}]*\}\s*from\s*"\.\/provider-label"/,
    );
  });

  it("names the house backend on the static surfaces", () => {
    expect(toStockChatPrefsConfig(DEFAULT_CLIENT_CONFIG).providerLabel).toBe(
      HOUSE_BACKEND_ID,
    );
  });
});
