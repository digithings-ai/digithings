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

  it("marks only the open thread with the ▸ arrow and the highlight", () => {
    const html = renderToStaticMarkup(
      <ChatThreadRows
        threads={[
          { status: "regular", id: "s1", title: "rates" },
          { status: "regular", id: "s2", title: "carry" },
        ]}
        activeId="s2"
        onSelect={() => {}}
      />,
    );
    const rows = html.split('<div class="nav-row"').slice(1);
    expect(rows).toHaveLength(2);
    const [first, second] = rows;
    expect(first).toContain("rates");
    expect(first).not.toContain("▸");
    expect(first).not.toContain('aria-current="true"');
    expect(first).not.toMatch(/nav-link[^"]* on\b/);
    expect(second).toContain("carry");
    expect(second).toContain('data-active="true"');
    expect(second).toContain("▸");
    expect(second).toContain('aria-current="true"');
    expect(second).toMatch(/nav-link[^"]* on\b/);
    expect(second).not.toContain("bg-transparent");
  });

  it("shows no marker when no thread is open", () => {
    const html = renderToStaticMarkup(
      <ChatThreadRows threads={[{ status: "regular", id: "s1", title: "rates" }]} onSelect={() => {}} />,
    );
    expect(html).not.toContain("▸");
    expect(html).not.toContain('aria-current="true"');
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
