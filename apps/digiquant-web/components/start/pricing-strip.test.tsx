import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StartBand } from "@/app/_bands/start";

describe("StartBand", () => {
  const html = renderToStaticMarkup(<StartBand />);

  it("keeps the real install commands and does not invent a managed price", () => {
    expect(html).toContain("digiquant[nautilus,mcp]");
    expect(html).toContain("digiquant.mcp_server --stdio --scope full");
    expect(html).toContain("Coming soon");
    expect(html).not.toMatch(/\$\d/);
  });
});
