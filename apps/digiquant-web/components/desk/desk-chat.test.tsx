import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DeskChat } from "./desk-chat";

describe("desk chat", () => {
  it("renders one loading line and no read footer or inner sidebar", () => {
    const html = renderToStaticMarkup(<DeskChat />);
    expect(html).toContain("loading…");
    expect(html).toContain('class="rail"');
    expect(html).not.toContain('aria-label="Conversations"');
    expect(html).not.toContain("Chat · sessions");
    expect(html).not.toContain("Chat · thread");
    expect(html).not.toContain("Chat · transcript");
    expect(html).not.toContain("digichat-thread-list");
    expect(html).not.toContain("scripted story");
    expect(html).not.toContain("scripted demo");
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("COMPOSER_HIDDEN");
  });
});