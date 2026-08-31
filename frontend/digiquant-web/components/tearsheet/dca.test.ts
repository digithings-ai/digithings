import { describe, expect, it } from "vitest";
import { hasTradeKpis, isDcaIndexEntry, isDcaTearsheet } from "./dca";
import { inferKind } from "./strategy-kinds";

describe("inferKind", () => {
  it("maps *_sdca slugs to dca and leaves slappers as long_short", () => {
    expect(inferKind("btc_sdca")).toBe("dca");
    expect(inferKind("eth_sdca")).toBe("dca");
    expect(inferKind("btc_slapper")).toBe("long_short");
    expect(inferKind("btc_sdca", "long_only")).toBe("long_only");
  });
});

describe("hasTradeKpis", () => {
  it("hides tiles when the schema reports null, not when the slug is sdca", () => {
    expect(hasTradeKpis(null, null)).toBe(false);
    expect(hasTradeKpis(0, 0)).toBe(true);
    expect(hasTradeKpis(62.5, 1.4)).toBe(true);
  });
});

describe("isDcaIndexEntry", () => {
  it("prefers vs_lump extras over the slug", () => {
    expect(isDcaIndexEntry({ strategy: "mystery", vs_lump_pct: -12 })).toBe(true);
    expect(isDcaIndexEntry({ strategy: "btc_slapper" })).toBe(false);
    expect(isDcaIndexEntry({ strategy: "btc_sdca" })).toBe(true);
  });
});

describe("isDcaTearsheet", () => {
  it("treats a dca block as authoritative", () => {
    expect(
      isDcaTearsheet({
        strategy: "btc_slapper",
        dca: { vs_lump_pct: 1 } as never,
      }),
    ).toBe(true);
    expect(isDcaTearsheet({ strategy: "btc_slapper" })).toBe(false);
  });
});
