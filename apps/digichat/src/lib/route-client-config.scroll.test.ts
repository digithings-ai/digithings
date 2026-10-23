import { describe, expect, it } from "vitest";
import { DEFAULT_CLIENT_CONFIG } from "./deploy-config/client-projection";
import { toStockChatPrefsConfig } from "./route-client-config";

/**
 * The app host builds its prefs from this projection. A field it forgets to
 * copy is indistinguishable from a field the deployment set to the default, so
 * the handoff is asserted here rather than left to the schema test.
 */
describe("toStockChatPrefsConfig chrome handoff", () => {
  it("carries the deploy scroll mode", () => {
    const free = {
      ...DEFAULT_CLIENT_CONFIG,
      chrome: { ...DEFAULT_CLIENT_CONFIG.chrome, scroll: { mode: "free" as const } },
    };
    expect(toStockChatPrefsConfig(free).scroll).toEqual({ mode: "free" });
    expect(toStockChatPrefsConfig(DEFAULT_CLIENT_CONFIG).scroll).toEqual({ mode: "follow" });
  });
});
