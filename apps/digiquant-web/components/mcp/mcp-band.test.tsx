import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { McpBand } from "@/app/_bands/mcp";
import { MCP_TOOLS } from "@/app/_mcp";

describe("McpBand", () => {
  const html = renderToStaticMarkup(<McpBand />);

  it("lists the registry and keeps execute as a demo until a gateway probe exists", () => {
    expect(MCP_TOOLS.length).toBeGreaterThan(0);
    expect(html).toContain(MCP_TOOLS[0].name);
    expect(html).toContain("demo · not executed");
    expect(html).toContain("Execute");
    expect(html).toContain("05 / mcp");
    expect(html).toContain("The tools are MCP tools");
    expect(html).not.toContain("digiquant · mcp");
    expect(html).not.toContain("↑↓ cycle tools");
    expect(html).not.toContain("from the repo");
    expect(html).not.toContain("connection succeeded");
  });
});
