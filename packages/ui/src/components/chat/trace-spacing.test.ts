import { describe, expect, it } from "vitest";
import {
  DEFAULT_TRACE_DENSITY,
  DENSITY_TOKENS,
  MOBILE_DEFAULT_DENSITY,
  MOBILE_DENSITY_QUERY,
  TRACE_DENSITIES,
  TRACE_SPACING,
  TRACE_SPACE_SCALE,
  matchesMobileDensityViewport,
  readStoredDensity,
  resolveTraceDensity,
  writeStoredDensity,
  type TraceDensity,
} from "./trace-spacing";

function rem(value: string): number {
  const match = value.match(/^(-?[\d.]+)rem$/);
  if (!match) throw new Error(`not a rem length: ${value}`);
  return Number(match[1]);
}

function em(value: string): number {
  const match = value.match(/^(-?[\d.]+)em$/);
  if (!match) throw new Error(`not an em tracking: ${value}`);
  return Number(match[1]);
}

describe("stored density", () => {
  function memory() {
    const map = new Map<string, string>();
    return {
      map,
      getItem: (k: string) => map.get(k) ?? null,
      setItem: (k: string, v: string) => void map.set(k, v),
    };
  }

  it("round-trips a choice through dt-density", () => {
    const store = memory();
    writeStoredDensity("airy", store);
    expect(store.map.get("dt-density")).toBe("airy");
    expect(readStoredDensity(store)).toBe("airy");
  });

  it("reads nothing for a missing or unknown value, and survives a throwing store", () => {
    const store = memory();
    expect(readStoredDensity(store)).toBeNull();
    store.map.set("dt-density", "huge");
    expect(readStoredDensity(store)).toBeNull();
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };
    expect(() => writeStoredDensity("compact", broken)).not.toThrow();
    expect(readStoredDensity(broken)).toBeNull();
  });
});

describe("resolveTraceDensity", () => {
  it("prefers a stored choice, then the deployment, then the builtin default", () => {
    expect(resolveTraceDensity("compact", "airy")).toBe("compact");
    expect(resolveTraceDensity(null, "airy")).toBe("airy");
    expect(resolveTraceDensity("  AIRY ", "compact")).toBe("airy");
    expect(resolveTraceDensity("roomy", "compact")).toBe("compact");
    expect(resolveTraceDensity("roomy", "nope")).toBe(DEFAULT_TRACE_DENSITY);
    expect(resolveTraceDensity(undefined, undefined)).toBe("default");
  });

  it("defaults a phone with no stored choice to airy", () => {
    expect(resolveTraceDensity(null, undefined, { mobile: true })).toBe(MOBILE_DEFAULT_DENSITY);
    expect(MOBILE_DEFAULT_DENSITY).toBe("airy");
    // The mobile default deliberately outranks a deployment default.
    expect(resolveTraceDensity(null, "compact", { mobile: true })).toBe("airy");
  });

  it("lets a stored choice win on mobile, including compact", () => {
    for (const density of TRACE_DENSITIES) {
      expect(resolveTraceDensity(density, "airy", { mobile: true })).toBe(density);
      expect(resolveTraceDensity(density, undefined, { mobile: true })).toBe(density);
    }
  });

  it("ignores an unknown stored value on mobile and falls back to airy", () => {
    expect(resolveTraceDensity("huge", "compact", { mobile: true })).toBe("airy");
    expect(resolveTraceDensity("", "compact", { mobile: true })).toBe("airy");
  });

  it("leaves desktop unchanged", () => {
    expect(resolveTraceDensity(null, undefined, { mobile: false })).toBe("default");
    expect(resolveTraceDensity(null, "compact", { mobile: false })).toBe("compact");
    // The old two-argument call is the desktop behaviour.
    expect(resolveTraceDensity(null, undefined)).toBe(
      resolveTraceDensity(null, undefined, { mobile: false }),
    );
    expect(resolveTraceDensity(null, "airy")).toBe(
      resolveTraceDensity(null, "airy", { mobile: false }),
    );
  });
});

describe("matchesMobileDensityViewport", () => {
  function viewport(matches: boolean, seen?: string[]) {
    return {
      matchMedia: (query: string) => {
        seen?.push(query);
        return { matches };
      },
    };
  }

  it("asks the documented phone breakpoint", () => {
    const seen: string[] = [];
    expect(matchesMobileDensityViewport(viewport(true, seen))).toBe(true);
    expect(seen).toEqual([MOBILE_DENSITY_QUERY]);
    expect(MOBILE_DENSITY_QUERY).toBe("(max-width: 640px)");
  });

  it("is never mobile without matchMedia or when the query throws", () => {
    expect(matchesMobileDensityViewport(null)).toBe(false);
    expect(matchesMobileDensityViewport({})).toBe(false);
    expect(
      matchesMobileDensityViewport({
        matchMedia: () => {
          throw new Error("blocked");
        },
      }),
    ).toBe(false);
    expect(matchesMobileDensityViewport(viewport(false))).toBe(false);
  });
});

describe("density tokens", () => {
  it("keeps every length on the scale, except a zero pad", () => {
    const scale = new Set<string>(Object.values(TRACE_SPACE_SCALE));
    for (const density of TRACE_DENSITIES) {
      const tokens = DENSITY_TOKENS[density];
      for (const [field, value] of Object.entries(tokens)) {
        if (field === "leading" || field === "leadingTight") continue;
        if (field === "tracking" || field === "trackingMono") continue;
        if (value === "0rem") {
          expect(field).toBe("pad");
          continue;
        }
        expect(scale.has(value)).toBe(true);
      }
    }
  });

  it("makes the three modes visibly distinct", () => {
    const ordered: TraceDensity[] = ["compact", "default", "airy"];
    for (const field of ["gap1", "gap2", "gap3", "gap4", "pad"] as const) {
      const values = ordered.map((density) => rem(DENSITY_TOKENS[density][field]));
      expect(values).toEqual([...values].sort((a, b) => a - b));
      expect(values[0]).toBeLessThan(values[1]);
      expect(values[1]).toBeLessThan(values[2]);
    }
    const leading = ordered.map((density) => Number(DENSITY_TOKENS[density].leading));
    expect(leading[0]).toBeLessThan(leading[1]);
    expect(leading[1]).toBeLessThan(leading[2]);
    const tracking = ordered.map((density) => em(DENSITY_TOKENS[density].tracking));
    expect(tracking[0]).toBeLessThan(tracking[1]);
    expect(tracking[1]).toBeLessThan(tracking[2]);
  });

  it("derives the semantic trace tokens from the density set", () => {
    for (const density of TRACE_DENSITIES) {
      const tokens = DENSITY_TOKENS[density];
      const trace = TRACE_SPACING[density];
      expect(trace.titleGap).toBe(tokens.gap3);
      expect(trace.groupGap).toBe(tokens.gap2);
      expect(trace.withinGap).toBe(tokens.gap1);
      expect(trace.bodyPad).toBe(tokens.pad);
      expect(trace.chainGap).toBe(tokens.gap4);
    }
    // A compact header sits flush; every other mode keeps a step.
    expect(TRACE_SPACING.compact.headerGap).toBe("0rem");
    for (const density of ["default", "airy"] as const) {
      expect(rem(TRACE_SPACING[density].headerGap)).toBeGreaterThan(0);
      expect(rem(TRACE_SPACING[density].bodyIndent)).toBeGreaterThan(0);
    }
  });
});
