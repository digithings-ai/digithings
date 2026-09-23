// @vitest-environment happy-dom
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import {
  AssistantRuntimeProvider,
  AuiConfig,
  Suggestions,
  useAui,
  useLocalRuntime,
} from "@assistant-ui/react";
import { act, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { DigichatThread, type GroupDisclosureMode } from "./DigichatThread";

const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

const SUGGESTION_CONFIG = AuiConfig({
  suggestions: Suggestions(["run a backtest"]),
});

const TOOL_MESSAGES: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "t1",
        toolName: "digisearch",
        argsText: "{}",
        result: "ok",
      },
      {
        type: "tool-call",
        toolCallId: "t2",
        toolName: "digivault_search_notes",
        argsText: "{}",
        result: "ok",
      },
      { type: "data", name: "status", data: { status: "started" } },
      {
        type: "source",
        sourceType: "url",
        id: "s1",
        url: "https://digithings.ai/docs",
        title: "docs",
      },
      { type: "text", text: "grounded answer" },
    ],
  },
];

const GLOOMBERB_MESSAGES: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "g1",
        toolName: "gloomberb_get_quote",
        argsText: '{"symbol":"AAPL"}',
        result: {
          result: {
            attribution: "Sourced from Gloomberb",
            delay_notice: "Data delayed up to 15 minutes",
            source_url: "https://term.gloom.sh/?ticker=AAPL",
          },
        },
      },
      { type: "text", text: "quote ready" },
    ],
  },
];

const GLOOMBERB_CLIPPED_MESSAGES: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "g3",
        toolName: "digiquant_digifetch_price_history",
        argsText: '{"symbol":"AAPL","resolution":"1d"}',
        // The shape digigraph emits post-#4131: §7 keys hoisted ahead of the
        // clipped scalar, so the attribution line renders without parsing text.
        result: {
          result: {
            attribution: "Sourced from Gloomberb",
            delay_notice: "Data delayed up to 15 minutes",
            source_url: "https://term.gloom.sh/?ticker=AAPL",
            ok: true,
            text: `${"x".repeat(2000)}… [truncated]`,
          },
        },
      },
      { type: "text", text: "history ready" },
    ],
  },
];

const UNATTRIBUTED_MESSAGES: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "u1",
        toolName: "yahoo_get_earnings_calendar",
        argsText: "{}",
        result: {
          result: { rows: [{ symbol: "AAPL", reportDate: "2026-09-18" }] },
        },
      },
      { type: "text", text: "calendar ready" },
    ],
  },
];

const REASONING_MESSAGES: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      { type: "reasoning", text: "thinking through the plan" },
      {
        type: "tool-call",
        toolCallId: "t1",
        toolName: "digisearch",
        argsText: "{}",
        result: "ok",
      },
      { type: "text", text: "grounded answer" },
    ],
  },
];

const TIMED_MESSAGE: ThreadMessageLike = {
  role: "assistant",
  content: [{ type: "text", text: "grounded answer" }],
  metadata: {
    timing: {
      streamStartTime: 0,
      firstTokenTime: 120,
      totalStreamTime: 2400,
      totalChunks: 12,
      toolCallCount: 2,
      tokenCount: 42,
      tokensPerSecond: 17.5,
    },
    custom: {
      usage: { inputTokens: 100, outputTokens: 42, totalTokens: 142 },
    },
  },
};

function AddComposerAttachment({ name }: { name: string }) {
  const aui = useAui();
  useEffect(() => {
    void aui.composer.addAttachment({
      name,
      type: "document",
      contentType: "text/html",
      content: [
        {
          type: "file",
          filename: name,
          data: "data:text/html;charset=utf-8,<p>snapshot</p>",
          mimeType: "text/html",
        },
      ],
    });
  }, [aui, name]);
  return null;
}

type HarnessProps = {
  body?: readonly string[];
  attachmentName?: string;
  hiddenAttachmentNames?: readonly string[];
  initialMessages?: readonly ThreadMessageLike[];
  reasoningMode?: GroupDisclosureMode;
  toolCallsMode?: GroupDisclosureMode;
};

function Harness({
  body,
  attachmentName,
  hiddenAttachmentNames,
  initialMessages,
  reasoningMode,
  toolCallsMode,
}: HarnessProps) {
  const runtime = useLocalRuntime(
    adapter,
    initialMessages ? { initialMessages } : undefined,
  );
  return (
    <AssistantRuntimeProvider runtime={runtime} config={SUGGESTION_CONFIG}>
      <DigichatThread
        welcome="inspect this"
        welcomeBody={body}
        placeholder="Ask digichat…"
        hiddenAttachmentNames={hiddenAttachmentNames}
        reasoningMode={reasoningMode}
        toolCallsMode={toolCallsMode}
      />
      {attachmentName ? <AddComposerAttachment name={attachmentName} /> : null}
    </AssistantRuntimeProvider>
  );
}

async function mount(props: HarnessProps = {}) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness {...props} />);
  });
  return {
    host,
    unmount: () => act(() => root.unmount()),
  };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("DigichatThread", () => {
  it("left-aligns the gallery Thread pane", async () => {
    const { host, unmount } = await mount();
    const thread = host.querySelector(".digichat-thread");
    expect(thread).toBeTruthy();
    expect(thread?.getAttribute("data-user-align")).toBe("left");
    expect(host.querySelector(".aui-root")).toBeTruthy();
    expect(host.textContent).toContain("inspect this");
    expect(host.querySelector('[aria-label="Message"]')).toBeTruthy();
    unmount();
  });

  it("docks welcome and example cubes in the footer above the composer", async () => {
    const { host, unmount } = await mount({
      body: ["Scoped to the tools and data in this deployment."],
    });
    const footer = host.querySelector(".digichat-thread__footer");
    const welcome = footer?.querySelector('[data-slot="aui_thread-welcome"]');
    const composer = footer?.querySelector('[aria-label="Message"]');
    expect(welcome).toBeTruthy();
    expect(composer).toBeTruthy();
    expect(host.querySelector(".digichat-thread__viewport > [data-slot='aui_thread-welcome']")).toBeNull();
    expect(footer?.textContent).toContain("inspect this");
    expect(footer?.textContent).toContain("Scoped to the tools and data in this deployment.");
    expect(footer?.textContent).toContain("run a backtest");
    expect(host.querySelector(".aui-composer-input")).toBeTruthy();
    expect(host.querySelector('[data-slot="aui_composer-shell"]')).toBeTruthy();
    expect(host.querySelector('[data-state="example"]')).toBeTruthy();
    expect(host.textContent).not.toContain("// digichat");
    expect(host.querySelector(".digichat-chip")).toBeNull();
    const footerHtml = footer?.innerHTML ?? "";
    expect(footerHtml.indexOf("aui_thread-welcome")).toBeGreaterThanOrEqual(0);
    expect(footerHtml.indexOf("aui_thread-welcome")).toBeLessThan(
      footerHtml.indexOf('aria-label="Message"'),
    );
    unmount();
  });

  it("renders a composer chip for a normal attachment", async () => {
    const { host, unmount } = await mount({ attachmentName: "user-file.txt" });
    await act(async () => {});
    expect(host.querySelector(".aui-attachment-root")).toBeTruthy();
    expect(host.textContent).toContain("user-file.txt");
    unmount();
  });

  it("hides the composer chip for names in hiddenAttachmentNames only", async () => {
    const hidden = await mount({
      attachmentName: "page-context.html",
      hiddenAttachmentNames: ["page-context.html"],
    });
    await act(async () => {});
    expect(hidden.host.querySelector(".aui-attachment-root")).toBeNull();
    // The attachment itself stays on the runtime — only the chip is hidden.
    hidden.unmount();

    const visible = await mount({
      attachmentName: "page-context.html",
      hiddenAttachmentNames: ["other-system-file.html"],
    });
    await act(async () => {});
    expect(visible.host.querySelector(".aui-attachment-root")).toBeTruthy();
    visible.unmount();
  });

  it("hides the sent-message file part for hidden names only", async () => {
    const filePart = {
      type: "file" as const,
      filename: "page-context.html",
      data: "data:text/html;charset=utf-8,<p>snapshot</p>",
      mimeType: "text/html",
    };
    const initialMessages: ThreadMessageLike[] = [
      { role: "user", content: [filePart] },
    ];

    const hidden = await mount({
      initialMessages,
      hiddenAttachmentNames: ["page-context.html"],
    });
    await act(async () => {});
    expect(
      hidden.host.querySelector('[data-slot="aui_user-message-file"]'),
    ).toBeNull();
    hidden.unmount();

    const visible = await mount({
      initialMessages,
      hiddenAttachmentNames: ["other-system-file.html"],
    });
    await act(async () => {});
    expect(
      visible.host.querySelector('[data-slot="aui_user-message-file"]'),
    ).toBeTruthy();
    visible.unmount();
  });

  it("collapses consecutive tool calls into a closed group by default", async () => {
    const { host, unmount } = await mount({ initialMessages: TOOL_MESSAGES });
    await act(async () => {});
    const group = host.querySelector('[data-slot="tool-group-root"]');
    expect(group).toBeTruthy();
    expect(group?.hasAttribute("data-closed")).toBe(true);
    const label = group?.querySelector('[data-slot="tool-group-trigger-label"]');
    expect(label?.textContent).toContain("2 tool calls");
    unmount();
  });

  it("opens the tool group when toolCallsMode is expanded", async () => {
    const { host, unmount } = await mount({
      initialMessages: TOOL_MESSAGES,
      toolCallsMode: "expanded",
    });
    await act(async () => {});
    expect(
      host
        .querySelector('[data-slot="tool-group-root"]')
        ?.hasAttribute("data-open"),
    ).toBe(true);
    unmount();
  });

  it("removes the tool group entirely when toolCallsMode is off", async () => {
    const { host, unmount } = await mount({
      initialMessages: TOOL_MESSAGES,
      toolCallsMode: "off",
    });
    await act(async () => {});
    expect(host.querySelector('[data-slot="tool-group-root"]')).toBeNull();
    expect(host.textContent).toContain("grounded answer");
    unmount();
  });

  it("renders reasoning in its own disclosure when reasoningMode is on", async () => {
    const { host, unmount } = await mount({
      initialMessages: REASONING_MESSAGES,
    });
    await act(async () => {});
    const reasoning = host.querySelector('[data-slot="reasoning-root"]');
    expect(reasoning).toBeTruthy();
    expect(reasoning?.hasAttribute("data-closed")).toBe(true);
    unmount();
  });

  it("hides reasoning when reasoningMode is off", async () => {
    const { host, unmount } = await mount({
      initialMessages: REASONING_MESSAGES,
      reasoningMode: "off",
    });
    await act(async () => {});
    expect(host.querySelector('[data-slot="reasoning-root"]')).toBeNull();
    unmount();
  });

  it("shows a message timing badge when timing metadata exists", async () => {
    const { host, unmount } = await mount({ initialMessages: [TIMED_MESSAGE] });
    await act(async () => {});
    const trigger = host.querySelector('[data-slot="message-timing-trigger"]');
    expect(trigger).toBeTruthy();
    expect(trigger?.textContent).toContain("2.4s");
    unmount();
  });

  it("omits the message timing badge when timing is absent", async () => {
    const { host, unmount } = await mount({
      initialMessages: [
        { role: "assistant", content: [{ type: "text", text: "no timing" }] },
      ],
    });
    await act(async () => {});
    expect(host.querySelector('[data-slot="message-timing-trigger"]')).toBeNull();
    unmount();
  });

  it("credits Gloomberb in the expanded tool result pane", async () => {
    const { host, unmount } = await mount({
      initialMessages: GLOOMBERB_MESSAGES,
      toolCallsMode: "expanded",
    });
    await act(async () => {});
    const trigger = host.querySelector('[data-slot="tool-fallback-trigger"]');
    expect(trigger).toBeTruthy();
    await act(async () => {
      trigger?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(host.textContent).toContain("Sourced from Gloomberb");
    expect(host.textContent).toContain("Data delayed up to 15 minutes");
    const link = host.querySelector(
      'a[href="https://term.gloom.sh/?ticker=AAPL"]',
    );
    expect(link).toBeTruthy();
    expect(link?.textContent).toContain("Open in Gloomberb");
    expect(link?.getAttribute("target")).toBe("_blank");
    expect(link?.getAttribute("rel")).toBe("noopener noreferrer");
    unmount();
  });

  it("credits Gloomberb when the tool result was clipped to its text preview", async () => {
    const { host, unmount } = await mount({
      initialMessages: GLOOMBERB_CLIPPED_MESSAGES,
      toolCallsMode: "expanded",
    });
    await act(async () => {});
    const trigger = host.querySelector('[data-slot="tool-fallback-trigger"]');
    expect(trigger).toBeTruthy();
    await act(async () => {
      trigger?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(host.textContent).toContain("Sourced from Gloomberb");
    expect(host.textContent).toContain("Data delayed up to 15 minutes");
    expect(
      host.querySelector('a[href="https://term.gloom.sh/?ticker=AAPL"]'),
    ).toBeTruthy();
    unmount();
  });

  it("omits the attribution line for tool results without an attribution block", async () => {
    const { host, unmount } = await mount({
      initialMessages: UNATTRIBUTED_MESSAGES,
      toolCallsMode: "expanded",
    });
    await act(async () => {});
    const trigger = host.querySelector('[data-slot="tool-fallback-trigger"]');
    expect(trigger).toBeTruthy();
    await act(async () => {
      trigger?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(host.querySelector('[data-slot="tool-fallback-result"]')).toBeTruthy();
    expect(host.querySelector('[data-slot="tool-fallback-attribution"]')).toBeNull();
    expect(host.textContent).not.toContain("Sourced from Gloomberb");
    unmount();
  });
});
