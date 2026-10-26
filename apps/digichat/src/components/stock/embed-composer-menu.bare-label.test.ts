import { describe, expect, it } from "vitest";
import { bareToolLabel } from "./embed-composer-menu";

/**
 * `/tools` and `/mcp` list tool names, so a note in parentheses at the end of
 * a name is dropped. The note is cut with a scan, not with a regex, because a
 * regex over a trailing bracket group backtracks in polynomial time on a name
 * whose group is never closed. These cases pin what the scan keeps and what
 * it drops.
 */
describe("bareToolLabel", () => {
  it("drops a trailing note and keeps the name", () => {
    expect(bareToolLabel("search_help (help docs)")).toBe("search_help");
    expect(bareToolLabel("Help search (help docs)")).toBe("Help search");
    expect(bareToolLabel("search_older (past tickets)")).toBe("search_older");
  });

  it("keeps a name that carries no note", () => {
    expect(bareToolLabel("search_help")).toBe("search_help");
    expect(bareToolLabel("  search_help  ")).toBe("search_help");
  });

  it("drops the last group and keeps the rest of the name", () => {
    expect(bareToolLabel("desk (tickets) (past tickets)")).toBe("desk (tickets)");
    expect(bareToolLabel("desk (tick(ets)")).toBe("desk (tick");
  });

  it("keeps a name whose group is not at the end", () => {
    expect(bareToolLabel("desk (tickets) reports")).toBe("desk (tickets) reports");
    expect(bareToolLabel("desk (tickets) extra")).toBe("desk (tickets) extra");
  });

  it("keeps a name that is nothing but the note", () => {
    expect(bareToolLabel("(help docs)")).toBe("(help docs)");
  });

  it("keeps a name whose group is never closed", () => {
    expect(bareToolLabel("desk (help docs")).toBe("desk (help docs");
  });

  it("cuts a long name that never closes its group in one pass", () => {
    // A regex over the trailing group backtracks in polynomial time on this
    // label and the test times out; the scan answers at once.
    const label = `${" ".repeat(100_000)}(${"b".repeat(100_000)}`;
    expect(bareToolLabel(label)).toBe(label.trim());
  });
});
