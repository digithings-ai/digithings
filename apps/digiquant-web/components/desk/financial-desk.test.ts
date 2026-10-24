import { describe, expect, it } from "vitest";
import { financialDesk, financialDeskLabel } from "./financial-desk";

describe("financial desk context", () => {
  it("uses the baseline desk run unless the caller is in FX Hub", () => {
    expect(financialDesk("/tools/digichat", null)).toBe("baseline");
    expect(financialDesk("/brief", "baseline")).toBe("baseline");
    expect(financialDesk("/tools/digichat", "fx")).toBe("fx");
    expect(financialDesk("/fx", null)).toBe("fx");
    expect(financialDesk("/fx/ideas", "baseline")).toBe("fx");
    expect(financialDeskLabel("baseline")).toBe("baseline desk run");
    expect(financialDeskLabel("fx")).toBe("FX Hub");
  });
});
