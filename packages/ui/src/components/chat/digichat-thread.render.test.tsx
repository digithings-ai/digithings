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
import { workVisibilityForView, type WorkVisibility } from "./stock/skin-types";

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

/**
 * Two work runs with only a source between them: one chain, not two.
 * The agent reasoned, called a tool, pulled a source, then reasoned and
 * called a tool again without writing anything in between.
 */
const TWO_RUNS_MESSAGES: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "r1",
        toolName: "digisearch",
        argsText: "{}",
        result: "ok",
      },
      {
        type: "source",
        sourceType: "url",
        id: "s9",
        url: "https://digithings.ai/docs",
        title: "docs",
      },
      {
        type: "tool-call",
        toolCallId: "r2",
        toolName: "digivault_get_note",
        argsText: "{}",
        result: "ok",
      },
      { type: "text", text: "one answer" },
    ],
  },
];

/**
 * Two tool runs with only a status part between them: one work block, and
 * the tool calls accumulate into one group.
 */
const TWO_TOOL_RUNS_MESSAGES: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "x1",
        toolName: "digisearch",
        argsText: "{}",
        result: "ok",
      },
      {
        type: "tool-call",
        toolCallId: "x2",
        toolName: "digivault_get_note",
        argsText: "{}",
        result: "ok",
      },
      { type: "data", name: "status", data: { status: "working" } },
      {
        type: "tool-call",
        toolCallId: "x3",
        toolName: "ticketing_list_tickets",
        argsText: "{}",
        result: "ok",
      },
      { type: "text", text: "done" },
    ],
  },
];

/**
 * The model explained itself, then went back to work: the first block is
 * finished, the second one is still working.
 */
const TEXT_THEN_WORK_MESSAGES: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "y1",
        toolName: "digisearch",
        argsText: "{}",
        result: "ok",
      },
      { type: "text", text: "Let me check the notes." },
      {
        type: "tool-call",
        toolCallId: "y2",
        toolName: "digivault_get_note",
        argsText: "{}",
        result: "ok",
      },
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
        toolName: "digifetch_quote",
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
        toolName: "digifetch_earnings_calendar",
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

/**
 * The agent only thought, then answered: a reasoning part with no tool call
 * in the turn. The work chain is still the disclosure boundary here — the
 * reasoning nests under it, so a quiet client folds this turn the same way
 * it folds a tool turn or a turn with both.
 */
const REASONING_ONLY_MESSAGES: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      { type: "reasoning", text: "thinking through the plan" },
      { type: "text", text: "grounded answer" },
    ],
  },
];

/**
 * The agent is still working: a tool call with no result, and the message
 * is still running. This is the one state where the quiet level and the
 * balanced level differ — quiet keeps the row shut while the work runs,
 * balanced opens it.
 */
const RUNNING_TOOL_MESSAGES: ThreadMessageLike[] = [
  {
    role: "assistant",
    status: { type: "running" },
    content: [
      {
        type: "tool-call",
        toolCallId: "run1",
        toolName: "digisearch",
        argsText: "{}",
      },
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
  workVisibility?: WorkVisibility;
};

function Harness({
  body,
  attachmentName,
  hiddenAttachmentNames,
  initialMessages,
  reasoningMode,
  toolCallsMode,
  workVisibility,
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
        workVisibility={workVisibility}
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

  it("folds the retired hidden level onto the titles-only chain", async () => {
    const { host, unmount } = await mount({
      initialMessages: TOOL_MESSAGES,
      // A stale host still says `hidden`; it means the folded chain now, and
      // the summary line it used to get is gone.
      workVisibility: workVisibilityForView("hidden" as never),
    });
    await act(async () => {});
    expect(host.querySelector('[data-slot="aui_work-chain-summary"]')).toBeNull();
    expect(host.querySelector('[data-slot="aui_work-chain"]')).toBeTruthy();
    expect(host.textContent).toContain("grounded answer");
    unmount();
  });

  it("shows the titles only when the client is quiet", async () => {
    const { host, unmount } = await mount({
      initialMessages: TOOL_MESSAGES,
      workVisibility: "quiet",
    });
    await act(async () => {});
    // The chain and its rows are there, folded.
    expect(host.querySelector('[data-slot="aui_work-chain"]')).toBeTruthy();
    const group = host.querySelector('[data-slot="tool-group-root"]');
    expect(group).toBeTruthy();
    expect(group?.hasAttribute("data-closed")).toBe(true);
    expect(host.querySelector('[data-slot="aui_work-chain-summary"]')).toBeNull();
    unmount();
  });

  it("shows no work block for a message that only carries a status part", async () => {
    // The connection state is a status part, and the grouping puts it in the
    // chain. Without the guard the chain header appeared before the model
    // had said anything — right next to the loading row.
    const { host, unmount } = await mount({
      initialMessages: [
        {
          role: "assistant",
          content: [
            { type: "data", name: "connection", data: { state: "connecting" } },
          ],
        },
      ],
    });
    await act(async () => {});
    expect(
      host.querySelector('[data-slot="aui_work-chain-trigger"]'),
    ).toBeNull();
    unmount();
  });

  it("folds the work the same way in every message shape when the client is quiet", async () => {
    // The chain is the outer disclosure boundary: every work part nests
    // under it, so a reasoning-only, a tool-only and a combined turn all
    // fold the same way. A quiet client sees the titles, never the work.
    const shapes = [
      {
        name: "reasoning only",
        messages: REASONING_ONLY_MESSAGES,
        rows: ['[data-slot="reasoning-root"]'],
        work: ["thinking through the plan"],
      },
      {
        name: "tool only",
        messages: TOOL_MESSAGES,
        rows: ['[data-slot="tool-group-root"]'],
        work: ["digisearch", "digivault_search_notes"],
      },
      {
        name: "reasoning and tool",
        messages: REASONING_MESSAGES,
        rows: ['[data-slot="reasoning-root"]', '[data-slot="tool-group-root"]'],
        work: ["thinking through the plan", "digisearch"],
      },
    ];
    for (const shape of shapes) {
      const { host, unmount } = await mount({
        initialMessages: shape.messages,
        workVisibility: "quiet",
      });
      await act(async () => {});
      // One chain per turn, and it is folded once the answer has started.
      const chains = host.querySelectorAll('[data-slot="aui_work-chain"]');
      expect(chains.length, shape.name).toBe(1);
      const chain = chains[0]!;
      expect(chain.hasAttribute("data-closed"), shape.name).toBe(true);
      for (const selector of shape.rows) {
        const row = host.querySelector(selector);
        expect(row, shape.name).toBeTruthy();
        // The row hangs inside the chain. That is what makes the level's
        // rule reach every shape of work.
        expect(chain.contains(row!), shape.name).toBe(true);
        expect(row!.hasAttribute("data-closed"), shape.name).toBe(true);
      }
      // And the work itself is not on the page.
      for (const text of shape.work) {
        expect(host.textContent, shape.name).not.toContain(text);
      }
      // The answer is still there: the fold takes the work, not the reply.
      expect(host.textContent, shape.name).toContain("grounded answer");
      unmount();
    }
  });

  it("keeps the work shut while the agent works when the client is quiet", async () => {
    // The one rule quiet carries alone: while the work runs, the rows stay
    // shut. The same turn under the balanced level opens the row, so the
    // assertion is about the level and not about the fixture.
    const { host, unmount } = await mount({
      initialMessages: RUNNING_TOOL_MESSAGES,
      workVisibility: "quiet",
    });
    await act(async () => {});
    const chain = host.querySelector('[data-slot="aui_work-chain"]');
    expect(chain).toBeTruthy();
    // The titles are the status line while the agent works, so the chain
    // is open; the row inside it is not.
    expect(chain?.hasAttribute("data-open")).toBe(true);
    const row = host.querySelector('[data-slot="tool-group-root"]');
    expect(row).toBeTruthy();
    expect(row?.hasAttribute("data-closed")).toBe(true);
    // The running tool is not on the page either.
    expect(host.textContent).not.toContain("Running tool: digisearch");
    unmount();

    // The control: the same turn under the balanced level opens the row.
    const balanced = await mount({
      initialMessages: RUNNING_TOOL_MESSAGES,
      workVisibility: "balanced",
    });
    await act(async () => {});
    expect(
      balanced.host
        .querySelector('[data-slot="tool-group-root"]')
        ?.hasAttribute("data-open"),
    ).toBe(true);
    balanced.unmount();
  });

  it("accumulates two tool runs into one group when only a status part separates them", async () => {
    const { host, unmount } = await mount({
      initialMessages: TWO_TOOL_RUNS_MESSAGES,
    });
    await act(async () => {});
    // One work block, one tool group, and the count is the tool calls.
    expect(
      host.querySelectorAll('[data-slot="aui_work-chain-trigger"]').length,
    ).toBe(1);
    const label = host.querySelector(
      '[data-slot="tool-group-trigger-label"]',
    );
    expect(label?.textContent).toContain("3 tool calls");
    unmount();
  });

  it("closes the finished block and keeps the new one working", async () => {
    const { host, unmount } = await mount({
      initialMessages: TEXT_THEN_WORK_MESSAGES,
    });
    await act(async () => {});
    const labels = Array.from(
      host.querySelectorAll('[data-slot="aui_work-status-label"]'),
    ).map((el) => el.textContent);
    // The block before the text is done — its folded title follows the last
    // step it took; the block after it is still working.
    expect(labels).toEqual(["Used 1 tool", "Working"]);
    unmount();
  });

  it("stops working once the answer starts, even while the turn streams", async () => {
    const { host, unmount } = await mount({ initialMessages: TOOL_MESSAGES });
    await act(async () => {});
    const label = host.querySelector('[data-slot="aui_work-status-label"]');
    // Folded, the title follows the last step: the work is done, so it says
    // what it did rather than sitting on a static "Worked".
    expect(label?.textContent).toBe("Used 2 tools");
    const marker = host.querySelector(
      '[data-slot="aui_work-chain-trigger"] [data-slot="dot-matrix"]',
    );
    expect(marker?.getAttribute("data-state")).not.toBe("loading");
    unmount();
  });

  it("folds the quiet chain as soon as the answer has started", async () => {
    // The titles are there while the agent works; when the answer streams
    // they get out of its way.
    const { host, unmount } = await mount({
      initialMessages: TOOL_MESSAGES,
      workVisibility: "quiet",
    });
    await act(async () => {});
    const chain = host.querySelector('[data-slot="aui_work-chain"]');
    expect(chain).toBeTruthy();
    expect(chain?.hasAttribute("data-closed")).toBe(true);
    unmount();
  });

  it("keeps the chain open when the client is verbose", async () => {
    const { host, unmount } = await mount({
      initialMessages: TOOL_MESSAGES,
      workVisibility: "verbose",
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
