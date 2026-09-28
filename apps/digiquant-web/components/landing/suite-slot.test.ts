import { describe, expect, it } from "vitest";
import { suiteSlotState } from "./suite-slot";

describe("suiteSlotState (#3447)", () => {
  it("shows a skeleton only before the strategy index resolves", () => {
    expect(suiteSlotState(false, undefined)).toBe("skeleton");
    expect(suiteSlotState(false, { strategy: "btc_slapper" })).toBe("skeleton");
  });

  it("renders the live card once the index has a row", () => {
    expect(suiteSlotState(true, { strategy: "btc_slapper" })).toBe("ready");
  });

  it("does not keep an unpublished slug (btc_sdca) as a KPI skeleton after the index loads", () => {
    expect(suiteSlotState(true, undefined)).toBe("unpublished");
  });
});
