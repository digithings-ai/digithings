import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatBand } from "@/app/_bands/chat";
import { COMPOSER_HIDDEN } from "@/components/chat/scripted-session";
import { PLAY_DONE, PLAY_START, nextCursor, project } from "@/app/_strategy-script";

describe("ChatBand", () => {
  const html = renderToStaticMarkup(<ChatBand />);

  it("mounts the digichat thread as a script, with the composer hidden", () => {
    expect(html).toContain("scripted · not a live session");
    expect(html).toContain("not connected to any MCP server");
    expect(html).toContain("digiquant_run_backtest");
    expect(html).toContain("digiquant_run_optimize");
    expect(html).toContain("digiquant_export");
    expect(html).toContain("scripted story");
    expect(html).toContain("scripted demo");
    expect(html).toContain("not a house book read");
    expect(html).toContain('data-thread-skin="digichat"');
    expect(html).toContain("digichat-thread-list");
    expect(html).toContain("3 tool calls");
    expect(html).toContain('data-slot="tool-fallback-result"');
    expect(html).toContain(COMPOSER_HIDDEN.replaceAll("&", "&amp;"));
    expect(html).toContain('aria-label="Message" disabled');
    expect(html).not.toContain("mean-revert spy");
    expect(html).not.toContain("edge report q3");
  });
});

describe("strategy script", () => {
  it("withholds a tool result while that call is running, then shows the chain", () => {
    const started = project(PLAY_START);
    expect(started.messages).toHaveLength(0);

    let cursor = PLAY_START;
    let sawRunningBacktest = false;
    for (let i = 0; i < 4000; i += 1) {
      const step = nextCursor(cursor);
      cursor = step.cursor;
      const view = project(cursor);
      const assistant = view.messages.find((message) => message.id === "assistant-chain");
      const content = assistant && Array.isArray(assistant.content) ? assistant.content : [];
      const backtest = content.find(
        (part) => part.type === "tool-call" && part.toolName === "digiquant_run_backtest",
      );
      if (backtest?.type === "tool-call" && backtest.result === undefined && view.running) {
        sawRunningBacktest = true;
      }
      if (step.done) break;
    }

    expect(sawRunningBacktest).toBe(true);
    const done = project(PLAY_DONE);
    const chain = done.messages.find((message) => message.id === "assistant-chain");
    expect(chain?.status).toEqual({ type: "complete", reason: "stop" });
    const tools =
      chain && Array.isArray(chain.content)
        ? chain.content.filter((part) => part.type === "tool-call").map((part) => part.toolName)
        : [];
    expect(tools).toEqual([
      "digiquant_list_strategies",
      "digiquant_run_backtest",
      "digiquant_run_optimize",
    ]);
    const blob = JSON.stringify(done.messages);
    expect(blob).not.toMatch(/p&l|sharpe|\bnav\b|price/i);
  });
});
