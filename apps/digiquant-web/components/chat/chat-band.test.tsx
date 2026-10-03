import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatBand } from "@/app/_bands/chat";
import {
  EXAMPLES,
  TOUR_HOLD_MS,
  doneCursor,
  exampleById,
  nextCursorFor,
  openCursor,
  projectTurns,
  shouldTakeOver,
  stepTour,
  type TourState,
} from "@/app/_strategy-script";
import { COMPOSER_HIDDEN } from "@/components/chat/scripted-session";

describe("ChatBand", () => {
  const html = renderToStaticMarkup(<ChatBand />);

  it("mounts the digichat thread with an example in each sidebar header", () => {
    for (const example of EXAMPLES) {
      expect(html).toContain(example.title);
    }
    expect(html).toContain("How do I start a trend-following strategy?");
    expect(html).toContain("digiquant_get_price_technicals");
    expect(html).toContain("digiquant_list_strategies");
    expect(html).toContain("digiquant_run_optimize");
    expect(html).toContain("digiquant_run_backtest");
    expect(html).toContain("Backtest completed");
    expect(html).toContain('data-thread-skin="digichat"');
    expect(html).toContain("Geist_Mono");
    expect(html).toContain("digichat-thread-list");
    expect(html).toContain(COMPOSER_HIDDEN.replaceAll("&", "&amp;"));
    expect(html).toContain('aria-label="Message" disabled');
    expect(html).not.toContain("scripted story");
    expect(html).not.toContain("scripted demo");
    expect(html).not.toContain("not a live session");
    expect(html).not.toContain("not connected to any MCP server");
    expect(html).not.toContain("house book");
  });

  it("loads Geist Mono for the digichat skin", () => {
    const font = readFileSync(new URL("./digichat-font.ts", import.meta.url), "utf8");
    const session = readFileSync(new URL("./scripted-session.tsx", import.meta.url), "utf8");
    expect(font).toContain('variable: "--font-geist-mono"');
    expect(font).toContain("Geist_Mono");
    expect(session).toContain("digichatFont.variable");
    expect(session).toContain('data-thread-skin="digichat"');
  });
});

describe("example chats", () => {
  it("withholds a tool result while that call is running, then posts the backtest", () => {
    const turns = exampleById("strategy").turns;
    let cursor = { turn: 0, part: 0, chars: 0, holding: false };
    let sawRunningBacktest = false;
    for (let i = 0; i < 8000; i += 1) {
      const step = nextCursorFor(turns, cursor);
      cursor = step.cursor;
      const view = projectTurns(turns, cursor);
      const assistant = view.messages.find((message) => message.id === "strategy-assistant");
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
    const done = projectTurns(turns, doneCursor(turns));
    const chain = done.messages.find((message) => message.id === "strategy-assistant");
    expect(chain?.status).toEqual({ type: "complete", reason: "stop" });
    const tools =
      chain && Array.isArray(chain.content)
        ? chain.content.filter((part) => part.type === "tool-call").map((part) => part.toolName)
        : [];
    expect(tools).toEqual([
      "digiquant_get_price_technicals",
      "digiquant_list_strategies",
      "digiquant_run_optimize",
      "digiquant_run_backtest",
    ]);
  });

  it("walks every sidebar chat, then wraps", () => {
    const order: string[] = [];
    let state: TourState = {
      id: "strategy",
      cursor: doneCursor(exampleById("strategy").turns),
    };
    for (let i = 0; i < EXAMPLES.length; i += 1) {
      const next = stepTour(state);
      expect(next.delay).toBe(280);
      state = { id: next.state.id, cursor: doneCursor(exampleById(next.state.id).turns) };
      order.push(next.state.id);
    }
    expect(order).toEqual(["research", "journal", "digest", "strategy"]);
    const held = stepTour({ id: "research", cursor: openCursor() });
    expect(held.state.id).toBe("research");
    expect(held.delay).not.toBe(TOUR_HOLD_MS);
  });

  it("uses Grokopedia on the research thread and stores the journal for a later pipeline read", () => {
    const research = projectTurns(exampleById("research").turns, doneCursor(exampleById("research").turns));
    const researchBlob = JSON.stringify(research.messages);
    expect(researchBlob).toContain("web_search");
    expect(researchBlob).toContain("grokipedia_search");
    expect(researchBlob).toContain("grokipedia_get_page");
    expect(researchBlob).toContain("Grokopedia");

    const journal = projectTurns(exampleById("journal").turns, doneCursor(exampleById("journal").turns));
    const journalBlob = JSON.stringify(journal.messages);
    expect(journalBlob).toContain("create_note");
    expect(journalBlob).toContain("search_notes");
    expect(journalBlob).toContain("digiquant_run_pipeline");
    expect(journalBlob).toContain("digichat memory");
    expect(journalBlob).toContain("trader profile");

    const digest = projectTurns(exampleById("digest").turns, doneCursor(exampleById("digest").turns));
    const digestBlob = JSON.stringify(digest.messages);
    expect(digestBlob).toContain("digiquant_query_research");
    expect(digestBlob).toContain("daily_snapshots");
    expect(digestBlob).toContain("Daily digest");
  });

  it("does not invent a house-book print", () => {
    const blob = EXAMPLES.map((example) =>
      JSON.stringify(projectTurns(example.turns, doneCursor(example.turns))),
    ).join("\n");
    expect(blob).not.toMatch(/sharpe|total_pnl|\bnav\b|house book|p&l/i);
    expect(blob).not.toMatch(/\d+(?:\.\d+)?%/);
  });

  it("stops the tour on a click, a key, a wheel, or a hover on a control", () => {
    expect(shouldTakeOver({ isTrusted: true, type: "pointerdown", control: false })).toBe(true);
    expect(shouldTakeOver({ isTrusted: true, type: "keydown", control: false })).toBe(true);
    expect(shouldTakeOver({ isTrusted: true, type: "wheel", control: false })).toBe(true);
    expect(shouldTakeOver({ isTrusted: true, type: "pointerover", control: true })).toBe(true);
    expect(shouldTakeOver({ isTrusted: true, type: "pointerover", control: false })).toBe(false);
    expect(shouldTakeOver({ isTrusted: false, type: "pointerdown", control: true })).toBe(false);
  });
});
