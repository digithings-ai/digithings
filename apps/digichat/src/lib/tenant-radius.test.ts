import { describe, expect, it } from "vitest";

import { parseTenantRadius, tenantRadiusCss } from "./tenant-radius";

describe("tenant radius", () => {
  it("is absent when the tenant sets none", () => {
    expect(parseTenantRadius(undefined, "t")).toBeUndefined();
    expect(tenantRadiusCss(null)).toBe("");
    expect(tenantRadiusCss({})).toBe("");
  });

  it("accepts whole pixels 0..48 per control", () => {
    expect(parseTenantRadius({ composer: 18, chip: 0 }, "t")).toEqual({ composer: 18, chip: 0 });
  });

  it("refuses units, fractions, out-of-range and unknown keys", () => {
    expect(() => parseTenantRadius({ composer: "18px" }, "t")).toThrow(/radius\.composer/);
    expect(() => parseTenantRadius({ composer: 12.5 }, "t")).toThrow(/radius\.composer/);
    expect(() => parseTenantRadius({ chip: -1 }, "t")).toThrow(/radius\.chip/);
    expect(() => parseTenantRadius({ chip: 49 }, "t")).toThrow(/radius\.chip/);
    expect(() => parseTenantRadius({ bubble: 8 }, "t")).toThrow();
  });

  it("sets the composer through the skin variable and the chips directly", () => {
    expect(tenantRadiusCss({ composer: 18 })).toBe(
      ":root:root .dc-embed-shell,:root:root .dc-embed-shell *{--composer-radius:18px}",
    );
    expect(tenantRadiusCss({ chip: 6 })).toBe(
      ":root:root .dc-embed-shell .aui-thread-welcome-suggestion{border-radius:6px}",
    );
  });
});
