import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CHAT_CLOSED, chatFailureSentence } from "../../../../clients/digiquant-tui/src/pages/chat-format";
import { ChatThreadRows } from "./chat-threads";

describe("desk chat threads", () => {
  it("lists real titles in the rail style and does not invent placeholders", () => {
    const html = renderToStaticMarkup(
      <ChatThreadRows
        threads={[
          { status: "regular", id: "s1", title: "rates" },
          { status: "regular", id: "s2", title: "—" },
        ]}
        activeId="s1"
        onSelect={() => {}}
      />,
    );
    expect(html).toContain('class="nav-title"');
    expect(html).toContain("threads");
    expect(html).toContain('class="nav-row"');
    expect(html).toContain('class="nav-path"');
    expect(html).toContain("rates");
    expect(html).toContain("—");
    expect(html).not.toContain("[wip]");
    expect(html).not.toContain("[soon]");
    expect(html).not.toContain("DIGICHAT");
  });

  it("renders nothing when the API returned no threads", () => {
    const html = renderToStaticMarkup(<ChatThreadRows threads={[]} onSelect={() => {}} />);
    expect(html).toBe("");
  });

  it("turns the three unconfigured reads into one sentence", () => {
    expect(
      chatFailureSentence([
        "/chat/sessions failed (502): digichat is not configured",
        "/chat/sessions/current failed (502): digichat is not configured",
        "/chat/sessions/current/messages failed (502): digichat is not configured",
      ]),
    ).toBe(CHAT_CLOSED);
    expect(CHAT_CLOSED).toBe("digichat is not configured.");
  });
});
