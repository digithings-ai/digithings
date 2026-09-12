import { describe, expect, it } from "vitest";
import { buildEmbedAccentStyle, isEmbedHexColor } from "./embed-accent-style";
import { readEmbedUiParams } from "./embed-ui-params";

describe("buildEmbedAccentStyle", () => {
  it("returns inline --accent for DataTap terracotta (regression)", () => {
    expect(buildEmbedAccentStyle("#b5562b", "#fff7f2")).toEqual({
      "--accent": "#b5562b",
      "--accent-foreground": "#fff7f2",
    });
  });

  it("returns undefined when color is missing — React omits style (bug symptom)", () => {
    expect(buildEmbedAccentStyle(undefined)).toBeUndefined();
    expect(buildEmbedAccentStyle(null)).toBeUndefined();
    expect(buildEmbedAccentStyle("")).toBeUndefined();
  });

  it("rejects non-hex so arbitrary URL values never reach a CSS var", () => {
    expect(buildEmbedAccentStyle("red")).toBeUndefined();
    expect(buildEmbedAccentStyle("#fff")).toBeUndefined();
    expect(buildEmbedAccentStyle("javascript:alert(1)")).toBeUndefined();
  });

  it("omits foreground when only color is valid", () => {
    expect(buildEmbedAccentStyle("#b5562b")).toEqual({ "--accent": "#b5562b" });
    expect(buildEmbedAccentStyle("#b5562b", "red")).toEqual({ "--accent": "#b5562b" });
  });

  it("round-trips DataTap ?accent=%23b5562b through parse → style", () => {
    const ui = readEmbedUiParams(
      "?accent=%23b5562b&accentForeground=%23fff7f2&welcome=Hello",
    );
    expect(ui.accent).toBe("#b5562b");
    expect(ui.welcome).toBe("Hello");
    expect(buildEmbedAccentStyle(ui.accent, ui.accentForeground)).toEqual({
      "--accent": "#b5562b",
      "--accent-foreground": "#fff7f2",
    });
  });
});

describe("isEmbedHexColor", () => {
  it("accepts #rrggbb only", () => {
    expect(isEmbedHexColor("#b5562b")).toBe(true);
    expect(isEmbedHexColor("#B5562B")).toBe(true);
    expect(isEmbedHexColor(undefined)).toBe(false);
    expect(isEmbedHexColor("#b5562")).toBe(false);
  });
});
