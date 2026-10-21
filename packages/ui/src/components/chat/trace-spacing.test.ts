import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_TRACE_DENSITY,
  TRACE_DENSITIES,
  TRACE_SPACING,
  TRACE_SPACE_SCALE,
  readStoredDensity,
  resolveTraceDensity,
  writeStoredDensity,
  type TraceSpacingTokens,
} from "./trace-spacing";

const SCALE_VAR: Record<string, string> = {
  "0rem": "0rem",
  "0.125rem": "var(--trace-space-1)",
  "0.25rem": "var(--trace-space-2)",
  "0.375rem": "var(--trace-space-3)",
  "0.5rem": "var(--trace-space-4)",
  "0.625rem": "var(--trace-space-5)",
  "0.75rem": "var(--trace-space-6)",
  "1rem": "var(--trace-space-7)",
};

const CSS_TOKEN: Record<keyof TraceSpacingTokens, string> = {
  titleGap: "--trace-title-gap",
  groupGap: "--trace-group-gap",
  withinGap: "--trace-within-gap",
  headerGap: "--trace-header-gap",
  bodyPad: "--trace-body-pad",
  bodyIndent: "--trace-body-indent",
  chainGap: "--trace-chain-gap",
};

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

  it("keeps every density length on the scale, except a zero header or body", () => {
    const scale = new Set<string>(Object.values(TRACE_SPACE_SCALE));
    for (const density of TRACE_DENSITIES) {
      for (const [token, length] of Object.entries(TRACE_SPACING[density])) {
        if (length === "0rem") {
          expect(["headerGap", "bodyPad"]).toContain(token);
          continue;
        }
        expect(scale.has(length)).toBe(true);
      }
    }
  });
});

describe("data-density css", () => {
  // Comments stripped, so a selector named in prose cannot satisfy a test.
  const css = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "..", "..", "styles", "chat-aui.css"),
    "utf8",
  ).replace(/\/\*[\s\S]*?\*\//g, "");

  function ruleFor(density: string): { selector: string; body: string } {
    const match = css.match(new RegExp(`([^{}]*data-density="${density}"[^{}]*)\\{([^{}]*)\\}`));
    return { selector: match?.[1] ?? "", body: match?.[2] ?? "" };
  }

  it("keys each density off the thread root the skin renders", () => {
    for (const density of TRACE_DENSITIES) {
      expect(ruleFor(density).selector).toContain(".digichat-thread");
    }
  });

  it("reassigns every semantic token from the same table the palette uses", () => {
    for (const density of TRACE_DENSITIES) {
      const body = ruleFor(density).body;
      for (const [token, length] of Object.entries(TRACE_SPACING[density]) as Array<
        [keyof TraceSpacingTokens, string]
      >) {
        expect(body).toContain(`${CSS_TOKEN[token]}: ${SCALE_VAR[length]}`);
      }
    }
  });
});
