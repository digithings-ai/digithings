import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_TRACE_DENSITY,
  TRACE_DENSITIES,
  TRACE_SPACING,
  TRACE_SPACE_SCALE,
  resolveTraceDensity,
  type TraceSpacingTokens,
} from "./trace-spacing";

const SCALE_VAR: Record<string, string> = {
  "0rem": "0rem",
  "0.125rem": "var(--space-1)",
  "0.25rem": "var(--space-2)",
  "0.375rem": "var(--space-3)",
  "0.5rem": "var(--space-4)",
  "0.625rem": "var(--space-5)",
  "0.75rem": "var(--space-6)",
  "1rem": "var(--space-7)",
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
  const css = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "..", "..", "styles", "chat-aui.css"),
    "utf8",
  );

  it("reassigns every semantic token from the same table the palette uses", () => {
    for (const density of TRACE_DENSITIES) {
      const block = css.match(
        new RegExp(`data-density="${density}"[\\s\\S]*?\\{([\\s\\S]*?)\\n\\}`),
      );
      const body = block?.[1] ?? "";
      for (const [token, length] of Object.entries(TRACE_SPACING[density]) as Array<
        [keyof TraceSpacingTokens, string]
      >) {
        expect(body).toContain(`${CSS_TOKEN[token]}: ${SCALE_VAR[length]}`);
      }
    }
  });
});
