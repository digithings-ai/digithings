/**
 * SSR smoke tests for the assistant turn's caret.
 *
 * Model: one bare flash cursor for the whole busy turn — under an empty wait,
 * under the growing tool chain, then under the streaming answer. Tool rows
 * carry their own running/ok state; we do not type "Working…" / "Searching…"
 * into a second indicator. Cursor gone when busy clears.
 *
 * Regression: waiting used to render BOTH a stream caret and a typed step
 * line (or a local "thinking …" + bouncing dots), so two indicators blinked
 * at once.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DigiChatSession } from "./DigiChatSession";
import type { DigiChatMessage, DigiChatSessionProps } from "./types";

function sessionWith(messages: DigiChatMessage[], busy: boolean): string {
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
  return renderToStaticMarkup(<DigiChatSession chat={chat} showIntro={false} />);
}

/** Typed step loader — must never appear; progress is the chain + bare caret. */
const STEP_LINE = "tl-line";
/** The bare streaming caret digichat dresses with .dt-cur. */
const STREAM_CARET = "dt-cur";

describe("assistant turn — busy", () => {
  it("shows a placeholder caret immediately after submit, before any assistant message exists", () => {
    const html = sessionWith([{ role: "user", content: "how does auth work" }], true);
    expect(html).toContain(STREAM_CARET);
    expect(html).toContain('aria-busy="true"');
    expect(html).not.toContain(STEP_LINE);
  });

  it("shows a bare cursor — not invented words — while waiting for the first event", () => {
    const html = sessionWith(
      [
        { role: "user", content: "how does auth work" },
        { role: "assistant", content: "" },
      ],
      true,
    );
    expect(html).toContain(STREAM_CARET);
    expect(html).not.toContain(STEP_LINE);
    // Real assistant row owns the caret — no second placeholder.
    expect(html).not.toContain('aria-busy="true"');
    for (const invented of ["thinking", "working", "routing through", "gathering context"]) {
      expect(html.toLowerCase()).not.toContain(invented);
    }
  });

  it("keeps the bare cursor under an in-flight tool chain (no typed status line)", () => {
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
    expect(html).toContain(STREAM_CARET);
    expect(html).not.toContain(STEP_LINE);
    expect(html).not.toContain("Searching for");
    expect(html).toContain("dc-activities");
    expect(html).toContain("azure_ai_search");
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
    expect(html).toContain(STREAM_CARET);
    expect(html).not.toContain(STEP_LINE);
  });

  it("strips ephemeral Working… from the chain while the caret still flashes", () => {
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
    expect(html).toContain(STREAM_CARET);
    expect(html).toContain("azure_ai_search");
    // Working… must not appear as a chain row (caret is unlabeled).
    expect(html).not.toMatch(/Working…/);
  });
});

describe("assistant turn — settled", () => {
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
    expect(html).toContain("azure_ai_search");
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
