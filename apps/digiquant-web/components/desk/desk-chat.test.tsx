import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DeskChat } from "./desk-chat";

describe("desk chat", () => {
  it("renders the digichat thread and the three official reads", () => {
    const html = renderToStaticMarkup(<DeskChat />);
    expect(html).toContain('aria-label="Conversations"');
    expect(html).toContain("Ask digichat…");
    expect(html).toContain("Chat · sessions");
    expect(html).toContain("/chat/sessions");
    expect(html).toContain("Chat · thread");
    expect(html).toContain("/chat/sessions/current");
    expect(html).toContain("Chat · transcript");
    expect(html).toContain("/chat/sessions/current/messages");
    expect(html).toContain("loading…");
    expect(html).not.toContain("scripted story");
    expect(html).not.toContain("scripted demo");
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("COMPOSER_HIDDEN");
  });
});