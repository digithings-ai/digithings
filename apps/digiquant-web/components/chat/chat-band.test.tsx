import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatBand } from "@/app/_bands/chat";

describe("ChatBand", () => {
  const html = renderToStaticMarkup(<ChatBand />);

  it("keeps the scripted story and says it is not a live session", () => {
    expect(html).toContain("scripted · not a live session");
    expect(html).toContain("not connected to any MCP server");
    expect(html).toContain("digiquant_run_backtest");
    expect(html).toContain("scripted story");
    expect(html).not.toContain("mean-revert spy");
    expect(html).not.toContain("edge report q3");
  });
});
