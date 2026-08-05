import { describe, it, expect } from "vitest";
import { resolveEmbedUiFlags } from "./embed-ui-flags";

describe("resolveEmbedUiFlags", () => {
  it("keeps showByok true under ungated", () => {
    expect(
      resolveEmbedUiFlags({
        slug: "digithings",
        gateMode: "ungated",
        theme: "dark",
        accent: null,
        attribution: false,
        showByok: true,
        showStatusBar: true,
        layout: "page",
      }),
    ).toEqual({ showByok: true, showStatusBar: true, layout: "page" });
  });

  it("does not derive showByok from gateMode", () => {
    expect(
      resolveEmbedUiFlags({
        slug: "x",
        gateMode: "turn_limited",
        theme: "dark",
        accent: null,
        attribution: false,
      }),
    ).toEqual({ showByok: false, showStatusBar: false, layout: "embed" });
  });
});
