// @vitest-environment happy-dom
/**
 * OCC regression: a digisearch + digivault_get_note turn streamed every
 * retrieve hit as its own top-level `source` part (and repeated the same
 * hits per retrieve span). The rows rendered inline between tool groups,
 * duplicated, and the message crashed with React #185 (max update depth).
 * Sources must render once, deduped, in a single footer outside the body.
 */
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime, type AssistantRuntime } from "@assistant-ui/react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DigichatThread } from "./DigichatThread";

const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

const HITS = [
  { title: "Cloud Portal manual > 2.2 Activating a new account", filename: "cloud-portal.md#2.2" },
  { title: "Erklarung Berechtigungen OCC_06.2026.pdf — page 1", url: "https://help.online-compliance-center.com/a.pdf" },
  { title: "OCC HelpCenter — Nächstes Wartungsfenster:", url: "https://help.online-compliance-center.com/index.php" },
  { title: "OCC Search manual > 12. Legal holds", filename: "occ-search.md#12" },
  { title: "User Guide_Search_OCC.pdf — page 3", url: "https://help.online-compliance-center.com/u.pdf" },
];

let n = 0;
function sources(withUrls: boolean): ThreadMessageLike["content"] {
  return HITS.map((h) =>
    h.url && withUrls
      ? { type: "source", sourceType: "url", id: `s${n++}`, url: h.url, title: h.title }
      : { type: "source", sourceType: "document", id: `s${n++}`, title: h.title, filename: h.filename ?? h.title, mediaType: "text/plain" },
  ) as unknown as ThreadMessageLike["content"];
}

const call = (id: string, toolName: string) => ({
  type: "tool-call" as const,
  toolCallId: id,
  toolName,
  argsText: "{}",
  result: { documents: HITS },
});

const MESSAGES: ThreadMessageLike[] = [
  { role: "user", content: [{ type: "text", text: "How do I activate an account?" }] },
  {
    role: "assistant",
    content: [
      call("t1", "digisearch"),
      call("t2", "digivault_get_note"),
      ...(sources(false) as never[]),
      ...(sources(true) as never[]),
      ...(sources(false) as never[]),
      call("t3", "digisearch"),
      call("t4", "digivault_get_note"),
      ...(sources(true) as never[]),
      { type: "text", text: "Activate via the welcome mail." },
    ] as ThreadMessageLike["content"],
  },
];

function Harness() {
  const runtime = useLocalRuntime(adapter, { initialMessages: MESSAGES });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <DigichatThread welcome="w" placeholder="p" />
    </AssistantRuntimeProvider>
  );
}

afterEach(() => document.body.replaceChildren());

describe("DigichatThread sources (digisearch + digivault_get_note)", () => {
  it("renders each source once in a footer, not inline, without an update loop", async () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(<Harness />);
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    const loop = errors.mock.calls.some((c) => /Maximum update depth|#185/.test(String(c[0])));
    errors.mockRestore();
    expect(loop).toBe(false);
    expect(host.textContent).toContain("Activate via the welcome mail.");

    const footer = host.querySelectorAll('[data-slot="aui_message-sources"]');
    expect(footer.length).toBe(1);
    const rows = footer[0]!.querySelectorAll(".aui-source-row");
    expect(rows.length).toBe(HITS.length);
    // A url-bearing copy of a hit wins over its url-less duplicate.
    expect(footer[0]!.querySelectorAll('a[data-slot="aui_source-url"]').length).toBe(3);
    // No source rows outside the footer (inline in the body).
    expect(host.querySelectorAll(".aui-source-row").length).toBe(HITS.length);
    act(() => root.unmount());
  });

  it("streams sources in many chunks without an update loop and keeps them out of the body", async () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const full = (MESSAGES[1]!.content as unknown[]).slice();
    const streaming: ChatModelAdapter = {
      async *run() {
        for (let i = 1; i <= full.length; i++) {
          await new Promise((r) => setTimeout(r, 2));
          yield { content: full.slice(0, i) as never };
        }
      },
    };
    let rt: AssistantRuntime | undefined;
    function StreamHarness() {
      const runtime = useLocalRuntime(streaming);
      rt = runtime;
      return (
        <AssistantRuntimeProvider runtime={runtime}>
          <DigichatThread welcome="w" placeholder="p" />
        </AssistantRuntimeProvider>
      );
    }
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(<StreamHarness />);
    });
    await act(async () => {
      rt!.thread.append({ role: "user", content: [{ type: "text", text: "How do I activate an account?" }] });
      await new Promise((r) => setTimeout(r, 300));
    });
    const loop = errors.mock.calls.some((c) => /Maximum update depth|#185/.test(String(c[0])));
    errors.mockRestore();
    expect(loop).toBe(false);
    expect(host.textContent).toContain("Activate via the welcome mail.");
    const footer = host.querySelectorAll('[data-slot="aui_message-sources"]');
    expect(footer.length).toBe(1);
    expect(host.querySelectorAll(".aui-source-row").length).toBe(HITS.length);
    act(() => root.unmount());
  });
});
