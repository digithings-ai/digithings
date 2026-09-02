/**
 * SSR smoke tests for the assistant turn's progress affordance.
 *
 * Model: a Searching… tool row until real activity arrives, then the chain,
 * then a caret under streaming prose. Cursor gone when busy clears.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DigiChatSession } from "./DigiChatSession";
import type { DigiChatMessage, DigiChatSessionProps } from "./types";

function sessionWith(
  messages: DigiChatMessage[],
  busy: boolean,
  layout: DigiChatSessionProps["layout"] = "page",
): string {
  const chat: DigiChatSessionProps["chat"] = {
    messages,
    busy,
    error: null,
    quotaPrompt: null,
    send: async () => {},
    stop: () => {},
    onRetry: () => {},
    modelLabel: "test-model",
  };
  return renderToStaticMarkup(
    <DigiChatSession chat={chat} showIntro={false} layout={layout} />,
  );
}

/** Typed step loader — must never appear; progress is the chain + Searching… row. */
const STEP_LINE = "tl-line";
/** The bare streaming caret digichat dresses with .dt-cur. */
const STREAM_CARET = "dt-cur";

describe("assistant turn — busy", () => {
  it("shows a Searching… row immediately after submit, before any assistant message exists", () => {
    const html = sessionWith([{ role: "user", content: "how does auth work" }], true);
    expect(html).toContain("Searching…");
    expect(html).toContain('aria-busy="true"');
    expect(html).not.toContain(STEP_LINE);
  });

  it("shows Searching… — not invented words — while waiting for the first event", () => {
    const html = sessionWith(
      [
        { role: "user", content: "how does auth work" },
        { role: "assistant", content: "" },
      ],
      true,
    );
    expect(html).toContain("Searching…");
    expect(html).not.toContain(STEP_LINE);
    expect(html).not.toContain('aria-busy="true"');
    for (const invented of ["thinking", "working", "routing through", "gathering context"]) {
      expect(html.toLowerCase()).not.toContain(invented);
    }
  });

  it("keeps the tool chain while a search is in flight (no typed status line)", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        {
          role: "assistant",
          content: "",
          activities: [{ kind: "tool_call", name: "azure_ai_search", query: "/api/config" }],
        },
      ],
      true,
    );
    expect(html).not.toContain(STEP_LINE);
    expect(html).not.toContain("Searching for");
    expect(html).toContain("dc-activities");
    expect(html).toContain("Search the knowledge base");
    expect(html).toContain("/api/config");
  });

  it("keeps the bare cursor under streaming prose", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        { role: "assistant", content: "Auth uses RS256." },
      ],
      true,
    );
    expect(html).toContain(STREAM_CARET);
    expect(html).not.toContain(STEP_LINE);
  });

  it("never mounts a typed step loader alongside the stream caret", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        {
          role: "assistant",
          content: "",
          activities: [{ kind: "trace", label: "Thinking", done: false }],
        },
      ],
      true,
    );
    expect(html).toContain("Thinking");
    expect(html).not.toContain(STEP_LINE);
  });

  it("strips ephemeral Working… from the chain", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        {
          role: "assistant",
          content: "",
          activities: [
            { kind: "trace", label: "Working…", done: false },
            { kind: "tool_call", name: "azure_ai_search", query: "docs" },
          ],
        },
      ],
      true,
    );
    expect(html).not.toContain(STEP_LINE);
    expect(html).toContain("Search the knowledge base");
    expect(html).not.toMatch(/Working…/);
  });
});

describe("assistant turn — settled", () => {
  it("places copy inside the body so it cannot overlap the notes counter", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        { role: "assistant", content: "Auth uses RS256." },
      ],
      false,
    );
    const bodyIdx = html.indexOf("dc-body");
    const copyIdx = html.indexOf("dc-msg-copy");
    expect(copyIdx).toBeGreaterThan(bodyIdx);
    expect(html).toContain("copy");
  });

  it("hides copy on embed — clipboard is blocked in the cross-origin iframe", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        { role: "assistant", content: "Auth uses RS256." },
      ],
      false,
      "embed",
    );
    expect(html).not.toContain("dc-msg-copy");
  });

  it("shows no caret when the turn is settled", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        { role: "assistant", content: "Done." },
      ],
      false,
    );
    expect(html).not.toContain(STEP_LINE);
    expect(html).not.toContain(STREAM_CARET);
  });

  it("strips Foundry 【N:M†source】 markers from the answer prose", () => {
    const html = sessionWith(
      [
        { role: "user", content: "how does auth work" },
        {
          role: "assistant",
          content: "Use the X-API-Key header\u30109:0\u2020source\u3011.",
          activities: [
            {
              kind: "tool_result",
              name: "azure_ai_search",
              query: "auth",
              count: 1,
              hits: [{ title: "page__docs___chunk0", path: "page__docs___chunk0", snippet: "Keys…" }],
            },
          ],
        },
      ],
      false,
    );
    expect(html).toContain("Use the X-API-Key header.");
    expect(html).not.toContain("\u3010");
    expect(html).not.toContain("dc-citations");
    expect(html).toContain("Search the knowledge base");
    expect(html).toContain("dc-source-cards");
  });
});

/**
 * #2529 / #3131 — model-remediable refusals must reopen BYOK settings even when
 * a key is already bound. The error-row link used to gate on `!providerIsSet`,
 * which left visitors with no escape hatch after binding a key without a model.
 */
describe("error row BYOK affordance (#2529)", () => {
  function errorHtml(opts: {
    showByok?: boolean;
    showByokOnError?: boolean;
    providerIsSet?: boolean;
  }): string {
    const chat: DigiChatSessionProps["chat"] = {
      messages: [],
      busy: false,
      error: "Your API key needs a model.",
      send: async () => {},
      stop: () => {},
      providerIsSet: opts.providerIsSet ?? false,
      openSettings: () => {},
    };
    return renderToStaticMarkup(
      <DigiChatSession
        chat={chat}
        showIntro={false}
        showByok={opts.showByok ?? true}
        showByokOnError={opts.showByokOnError}
        welcomeIntro=""
        placeholder="Ask…"
      />,
    );
  }

  it("offers Update your API key when a key is already bound", () => {
    const html = errorHtml({ providerIsSet: true, showByokOnError: true });
    expect(html).toContain("Update your API key");
    expect(html).not.toContain("Add your API key");
  });

  it("offers Add your API key when no key is bound yet", () => {
    const html = errorHtml({ providerIsSet: false, showByokOnError: true });
    expect(html).toContain("Add your API key");
    expect(html).not.toContain("Update your API key");
  });

  it("hides the BYOK link when showByokOnError is false (infra / ungated)", () => {
    const html = errorHtml({
      providerIsSet: true,
      showByok: true,
      showByokOnError: false,
    });
    expect(html).toContain("Your API key needs a model.");
    expect(html).not.toContain("Update your API key");
    expect(html).not.toContain("Add your API key");
  });
});
