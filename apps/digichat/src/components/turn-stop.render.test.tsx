// @vitest-environment happy-dom
/**
 * A stopped or failed turn stops every animation it started (DIG-4459).
 *
 * Production wiring with a mocked stream: useChat + useAISDKRuntime +
 * DefaultChatTransport over a fetch that returns a hand-fed UI message stream.
 * Nothing leaves the process and no model is called.
 */
import { useChat } from "@ai-sdk/react";
import { useAISDKRuntime } from "@assistant-ui/ai-sdk";
import { AssistantRuntimeProvider, useAui } from "@assistant-ui/react";
import { DefaultChatTransport } from "ai";
import { act, useEffect, useState, type FC } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { DigichatThread } from "@digithings/ui/chat/thread";

type Chunk = Record<string, unknown>;

/** A /api/chat stand-in: the test pushes chunks, ends, or waits for the abort. */
function mockStream() {
  let controller: ReadableStreamDefaultController<Uint8Array> | null = null;
  const pending: string[] = [];
  const enc = new TextEncoder();
  let aborted = false;
  const write = (line: string) => {
    if (controller) controller.enqueue(enc.encode(line));
    else pending.push(line);
  };
  const fetchImpl = async (_url: RequestInfo | URL, init?: RequestInit) => {
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c;
        for (const line of pending.splice(0)) c.enqueue(enc.encode(line));
      },
    });
    init?.signal?.addEventListener("abort", () => {
      aborted = true;
      try {
        controller?.error(new DOMException("aborted", "AbortError"));
      } catch {
        /* already closed */
      }
    });
    return new Response(body, {
      status: 200,
      headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" },
    });
  };
  return {
    fetchImpl,
    send: (chunk: Chunk) => write(`data: ${JSON.stringify(chunk)}\n\n`),
    end: () => {
      write("data: [DONE]\n\n");
      controller?.close();
    },
    wasAborted: () => aborted,
  };
}

const settle = (ms = 40) =>
  act(async () => {
    await new Promise((r) => setTimeout(r, ms));
  });

async function mount(fetchImpl: typeof fetch) {
  let aui: ReturnType<typeof useAui> | null = null;
  const Grab: FC = () => {
    const a = useAui();
    useEffect(() => {
      aui = a;
      a.thread().append("How do I reset my password?");
    }, [a]);
    return null;
  };
  const Harness: FC = () => {
    const [transport] = useState(() => new DefaultChatTransport({ api: "/api/chat", fetch: fetchImpl }));
    const chat = useChat({ transport });
    const runtime = useAISDKRuntime(chat);
    return (
      <AssistantRuntimeProvider runtime={runtime}>
        <DigichatThread placeholder="Ask digichat…" />
        <Grab />
      </AssistantRuntimeProvider>
    );
  };
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness />);
  });
  await settle();
  return {
    host,
    stop: async () => {
      await act(async () => {
        aui!.thread().cancelRun();
      });
      await settle(80);
    },
    unmount: () => act(() => root.unmount()),
  };
}

/** Multi-frame glyphs: any of these inside the turn is an animation still running. */
// ("tools", "thought" and "idle" are single-frame glyphs and never animate.)
const ANIMATED = ["loading", "thinking", "tool", "executing", "searching", "compacting"];

function assistant(host: HTMLElement) {
  const turns = host.querySelectorAll("[data-role='assistant']");
  return turns[turns.length - 1] as HTMLElement | undefined;
}

function liveAnimations(root: HTMLElement | undefined) {
  if (!root) return [];
  const glyphs = [...root.querySelectorAll("[data-slot='dot-matrix']")]
    .map((m) => m.getAttribute("data-state") ?? "")
    .filter((state) => ANIMATED.includes(state));
  const shimmer = root.querySelectorAll(".shimmer").length;
  const indicator = root.querySelectorAll("[data-slot='aui_assistant-message-indicator']").length;
  return [...glyphs, ...(shimmer ? ["shimmer"] : []), ...(indicator ? ["indicator"] : [])];
}

function chainHeader(root: HTMLElement | undefined) {
  const chain = root?.querySelector("[data-slot='aui_work-chain']");
  return {
    outcome: chain?.getAttribute("data-outcome") ?? null,
    title: chain?.querySelector("[data-slot='aui_work-status-label']")?.textContent ?? null,
    marker:
      chain?.querySelector("[data-slot='aui_work-status-marker'] [data-slot='dot-matrix']")?.getAttribute("data-state") ??
      null,
  };
}

function openToolCall(s: ReturnType<typeof mockStream>) {
  s.send({ type: "start", messageId: "m1" });
  s.send({ type: "start-step" });
  s.send({ type: "reasoning-start", id: "r1" });
  s.send({ type: "reasoning-delta", id: "r1", delta: "Looking it up." });
  s.send({ type: "tool-input-start", toolCallId: "c1", toolName: "digisearch" });
  s.send({ type: "tool-input-available", toolCallId: "c1", toolName: "digisearch", input: { query: "reset" } });
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("a stopped or failed turn stops its animations", () => {
  it("error mid-stream: the chain says Failed, the tool row failed, nothing animates", async () => {
    const s = mockStream();
    const { host, unmount } = await mount(s.fetchImpl as typeof fetch);
    openToolCall(s);
    await settle();
    // Sanity: while the call is open the turn animates.
    expect(liveAnimations(assistant(host)).length).toBeGreaterThan(0);
    expect(chainHeader(assistant(host)).title).toBe("Working");

    s.send({ type: "error", errorText: "Upstream failed (mock)" });
    s.end();
    await settle(80);

    const turn = assistant(host);
    expect(chainHeader(turn)).toEqual({ outcome: "failed", title: "Failed", marker: "error" });
    expect(liveAnimations(turn)).toEqual([]);
    expect(turn?.textContent).not.toMatch(/Running tool|Waiting on tool|Working/);
    unmount();
  });

  it("abort mid-tool-call: the chain says Stopped, the tool row is cancelled, nothing animates", async () => {
    const s = mockStream();
    const { host, stop, unmount } = await mount(s.fetchImpl as typeof fetch);
    openToolCall(s);
    await settle();
    expect(liveAnimations(assistant(host)).length).toBeGreaterThan(0);

    await stop();
    expect(s.wasAborted()).toBe(true);
    const turn = assistant(host);
    expect(chainHeader(turn)).toEqual({ outcome: "stopped", title: "Stopped", marker: "stop" });
    expect(liveAnimations(turn)).toEqual([]);
    expect(turn?.textContent).not.toMatch(/Running tool|Waiting on tool|Working/);
    unmount();
  });

  it("abort before the first token: no loader, no chain, nothing animates", async () => {
    const s = mockStream();
    const { host, stop, unmount } = await mount(s.fetchImpl as typeof fetch);
    await settle();
    await stop();
    expect(s.wasAborted()).toBe(true);
    expect(liveAnimations(assistant(host))).toEqual([]);
    expect(host.querySelector("[data-slot='aui_assistant-message-indicator']")).toBeNull();
    expect(host.querySelector("[data-slot='aui_work-chain']")).toBeNull();
    unmount();
  });

  it("abort while the server reports a wait: the status row goes away", async () => {
    const s = mockStream();
    const { host, stop, unmount } = await mount(s.fetchImpl as typeof fetch);
    s.send({ type: "start", messageId: "m1" });
    s.send({ type: "data-connection", id: "conn", data: { state: "waiting", message: "Waiting for capacity…" } });
    await settle();
    await stop();
    expect(liveAnimations(assistant(host))).toEqual([]);
    expect(host.textContent).not.toContain("Waiting for capacity");
    unmount();
  });

  it("a finished turn still reads Worked", async () => {
    const s = mockStream();
    const { host, unmount } = await mount(s.fetchImpl as typeof fetch);
    openToolCall(s);
    s.send({ type: "tool-output-available", toolCallId: "c1", output: { hits: 1 } });
    s.send({ type: "reasoning-end", id: "r1" });
    s.send({ type: "text-start", id: "t1" });
    s.send({ type: "text-delta", id: "t1", delta: "Use the reset link." });
    s.send({ type: "text-end", id: "t1" });
    s.send({ type: "finish-step" });
    s.send({ type: "finish" });
    s.end();
    await settle(800);
    const turn = assistant(host);
    expect(chainHeader(turn).outcome).toBe("done");
    expect(liveAnimations(turn)).toEqual([]);
    unmount();
  });
});
