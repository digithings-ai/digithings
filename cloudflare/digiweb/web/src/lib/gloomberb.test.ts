import { describe, expect, it } from "vitest";

import {
  GLOOMBERB_ATTRIBUTION,
  GLOOMBERB_DELAY_NOTICE,
  GLOOMBERB_TERMINAL_URL,
  gloomberbTickerUrl,
  readGloomberbAttribution,
} from "./gloomberb";

describe("gloomberb conventions", () => {
  it("pins the canonical strings mirrored from attribution.py", () => {
    expect(GLOOMBERB_ATTRIBUTION).toBe("Sourced from Gloomberb");
    expect(GLOOMBERB_DELAY_NOTICE).toBe("Data delayed up to 15 minutes");
    expect(GLOOMBERB_TERMINAL_URL).toBe("https://term.gloom.sh/");
  });

  it("builds ?ticker= deep links with the symbol encoded", () => {
    expect(gloomberbTickerUrl("BRK.B")).toBe("https://term.gloom.sh/?ticker=BRK.B");
    expect(gloomberbTickerUrl("BTC-USD")).toBe(
      "https://term.gloom.sh/?ticker=BTC-USD",
    );
    expect(gloomberbTickerUrl(" AAPL ")).toBe("https://term.gloom.sh/?ticker=AAPL");
    expect(gloomberbTickerUrl("A/B C")).toBe("https://term.gloom.sh/?ticker=A%2FB%20C");
  });

  it("extracts the attribution block from a digifetch envelope", () => {
    expect(
      readGloomberbAttribution({
        result: {
          attribution: "Sourced from Gloomberb",
          delay_notice: "Data delayed up to 15 minutes",
          source_url: "https://term.gloom.sh/?ticker=AAPL",
        },
      }),
    ).toEqual({
      attribution: "Sourced from Gloomberb",
      delayNotice: "Data delayed up to 15 minutes",
      sourceUrl: "https://term.gloom.sh/?ticker=AAPL",
    });
  });

  it("extracts the attribution block from a JSON string result", () => {
    expect(
      readGloomberbAttribution(
        JSON.stringify({
          result: {
            attribution: "Sourced from Gloomberb",
            delay_notice: "Data delayed up to 15 minutes",
            source_url: "https://term.gloom.sh/?ticker=BTC-USD",
          },
        }),
      ),
    ).toEqual({
      attribution: "Sourced from Gloomberb",
      delayNotice: "Data delayed up to 15 minutes",
      sourceUrl: "https://term.gloom.sh/?ticker=BTC-USD",
    });
  });

  it("tolerates a missing delay notice or source link", () => {
    expect(readGloomberbAttribution({ attribution: "Sourced from Gloomberb" })).toEqual(
      { attribution: "Sourced from Gloomberb", delayNotice: undefined, sourceUrl: undefined },
    );
  });

  it("returns null for unattributed payloads (earnings-calendar shape)", () => {
    expect(
      readGloomberbAttribution({
        result: { rows: [{ symbol: "AAPL", reportDate: "2026-09-18" }], truncated: false },
      }),
    ).toBeNull();
    expect(readGloomberbAttribution({ rows: [] })).toBeNull();
    expect(readGloomberbAttribution("ok")).toBeNull();
    expect(readGloomberbAttribution(null)).toBeNull();
    expect(readGloomberbAttribution(undefined)).toBeNull();
  });
});
