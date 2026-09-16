import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  GLOOMBERB_ATTRIBUTION,
  GLOOMBERB_DELAY_NOTICE,
  GLOOMBERB_TERMINAL_URL,
  gloomberbTickerUrl,
  readGloomberbAttribution,
} from "./gloomberb";

const here = dirname(fileURLToPath(import.meta.url));

function readRepoFile(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

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

  it("treats a blank attribution string as absent", () => {
    expect(readGloomberbAttribution({ attribution: "" })).toBeNull();
    expect(readGloomberbAttribution({ attribution: "   " })).toBeNull();
    expect(readGloomberbAttribution({ result: { attribution: "\t\n" } })).toBeNull();
  });

  it("drops a source link that is not on the Gloomberb terminal", () => {
    expect(
      readGloomberbAttribution({
        attribution: "Sourced from Gloomberb",
        source_url: "https://evil.example/?ticker=AAPL",
      }),
    ).toEqual({
      attribution: "Sourced from Gloomberb",
      delayNotice: undefined,
      sourceUrl: undefined,
    });
    expect(
      readGloomberbAttribution({
        attribution: "Sourced from Gloomberb",
        source_url: "https://term.gloom.sh.evil.example/?ticker=AAPL",
      })?.sourceUrl,
    ).toBeUndefined();
    expect(
      readGloomberbAttribution({
        attribution: "Sourced from Gloomberb",
        source_url: "https://term.gloom.sh/?ticker=AAPL",
      })?.sourceUrl,
    ).toBe("https://term.gloom.sh/?ticker=AAPL");
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

describe("gloomberb conventions — cross-language parity", () => {
  const PYTHON_ATTRIBUTION = "../../../../../digiquant/src/digiquant/data/gloomberb/attribution.py";

  function pythonConstant(name: string): string {
    const source = readRepoFile(PYTHON_ATTRIBUTION);
    const match = source.match(new RegExp(`^${name}\\s*=\\s*"([^"]*)"`, "m"));
    if (!match) throw new Error(`${name} not found in attribution.py`);
    return match[1];
  }

  it("matches the attribution.py constant values", () => {
    expect(GLOOMBERB_ATTRIBUTION).toBe(pythonConstant("GLOOMBERB_ATTRIBUTION"));
    expect(GLOOMBERB_DELAY_NOTICE).toBe(pythonConstant("GLOOMBERB_DELAY_NOTICE"));
    expect(GLOOMBERB_TERMINAL_URL).toBe(pythonConstant("GLOOMBERB_TERMINAL_URL"));
  });

  it("builds the same ?ticker= deep link as terminal_ticker_url()", () => {
    expect(readRepoFile(PYTHON_ATTRIBUTION)).toMatch(/\?ticker=/);
    expect(gloomberbTickerUrl("AAPL")).toBe(
      `${pythonConstant("GLOOMBERB_TERMINAL_URL")}?ticker=AAPL`,
    );
  });
});
