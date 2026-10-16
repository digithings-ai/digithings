import { describe, expect, it } from "vitest";
import { toolRowTitle } from "./tool-display";

describe("toolRowTitle", () => {
  it("keeps the exact backend tool id, including underscores", () => {
    expect(toolRowTitle("digisearch")).toBe("digisearch");
    expect(toolRowTitle("digivault_get_note")).toBe("digivault_get_note");
    expect(toolRowTitle("digivault_search_notes")).toBe("digivault_search_notes");
    expect(toolRowTitle("web_search")).toBe("web_search");
  });

  it("keeps fetch_all and research ids verbatim", () => {
    expect(toolRowTitle("digisearch_fetch_all")).toBe("digisearch_fetch_all");
    expect(toolRowTitle("digisearch_research")).toBe("digisearch_research");
  });

  it("titles tenant per-index digisearch tools readably (DIG-3269)", () => {
    expect(toolRowTitle("digisearch_zammad_tickets")).toBe("DigiSearch Zammad Tickets");
    expect(toolRowTitle("digisearch_occ_help")).toBe("DigiSearch OCC Help");
  });

  it("falls back to 'tool' for a blank id", () => {
    expect(toolRowTitle("   ")).toBe("tool");
  });
});
