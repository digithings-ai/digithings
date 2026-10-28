import { describe, expect, it } from "vitest";
import {
  PRIVATE_REASONING_TEXT,
  PRIVATE_TERM_LABEL,
  PRIVATE_TOOL_ERROR,
  PrivateTextScrubber,
  privateTermsFor,
  privatizeChatResponse,
  privatizeChunk,
} from "./private-stream";

function sse(chunks: Array<unknown | string>): string {
  return chunks
    .map((chunk) => `data: ${typeof chunk === "string" ? chunk : JSON.stringify(chunk)}\n\n`)
    .join("");
}

function streamOf(body: string, pieceSize = 7): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(body);
  return new ReadableStream({
    start(controller) {
      for (let at = 0; at < bytes.length; at += pieceSize) {
        controller.enqueue(bytes.slice(at, at + pieceSize));
      }
      controller.close();
    },
  });
}

async function readEvents(res: Response): Promise<Array<Record<string, unknown> | string>> {
  const text = await res.text();
  return text
    .split("\n\n")
    .filter(Boolean)
    .map((event) => event.replace(/^data: /, ""))
    .map((payload) => {
      try {
        return JSON.parse(payload) as Record<string, unknown>;
      } catch {
        return payload;
      }
    });
}

describe("privateTermsFor", () => {
  it("collects the slug and MCP server ids, skipping short and generic ones", () => {
    expect(
      privateTermsFor({
        slug: "acmehelp",
        mcp: { servers: [{ id: "deskly" }, { id: "x" }, { id: "embed" }] },
      }),
    ).toEqual(["acmehelp", "deskly"]);
    expect(privateTermsFor(null)).toEqual([]);
  });
});

describe("PrivateTextScrubber", () => {
  it("replaces emails and phone numbers with consistent placeholders", () => {
    const s = new PrivateTextScrubber();
    const out = s.scrub(
      "Mail jane.doe@client.example or call +39 333 123 4567. Again: JANE.DOE@client.example",
    );
    expect(out).not.toContain("jane.doe");
    expect(out).not.toContain("123 4567");
    expect(out).toBe(
      "Mail contact1@example.com or call +1 555 0100. Again: contact1@example.com",
    );
  });

  it("leaves dates, times and short ids alone", () => {
    const s = new PrivateTextScrubber();
    const text = "Ticket 10045 opened 2026-10-28 at 14:30, priority 2.";
    expect(s.scrub(text)).toBe(text);
  });

  it("replaces the tenant's own names and strips them from tool names", () => {
    const s = new PrivateTextScrubber(["acmehelp", "deskly"]);
    expect(s.scrub("Welcome to AcmeHelp, synced from Deskly.")).toBe(
      `Welcome to ${PRIVATE_TERM_LABEL}, synced from ${PRIVATE_TERM_LABEL}.`,
    );
    expect(s.toolName("deskly_search_tickets")).toBe("search_tickets");
    expect(s.toolName("deskly")).toBe("tool");
    expect(s.toolName("search_docs")).toBe("search_docs");
  });
});

describe("privatizeChunk", () => {
  const s = new PrivateTextScrubber(["deskly"]);

  it("drops reasoning text, tool input deltas and sources", () => {
    for (const type of ["reasoning-delta", "tool-input-delta", "source-url", "source-document"]) {
      expect(privatizeChunk({ type, delta: "secret" }, s)).toBeNull();
    }
  });

  it("keeps only the ids and outcome of a tool step", () => {
    expect(
      privatizeChunk(
        { type: "tool-input-start", toolCallId: "c1", toolName: "deskly_search", title: "Jane" },
        s,
      ),
    ).toEqual({ type: "tool-input-start", toolCallId: "c1", toolName: "search" });
    expect(
      privatizeChunk(
        {
          type: "tool-input-available",
          toolCallId: "c1",
          toolName: "deskly_search",
          input: { q: "Jane Doe" },
          providerMetadata: { x: 1 },
        },
        s,
      ),
    ).toEqual({ type: "tool-input-available", toolCallId: "c1", toolName: "search", input: {} });
    expect(
      privatizeChunk({ type: "tool-output-available", toolCallId: "c1", output: { a: 1 } }, s),
    ).toEqual({ type: "tool-output-available", toolCallId: "c1", output: {} });
    expect(
      privatizeChunk({ type: "tool-output-error", toolCallId: "c1", errorText: "jane@x.io 404" }, s),
    ).toEqual({ type: "tool-output-error", toolCallId: "c1", errorText: PRIVATE_TOOL_ERROR });
  });

  it("keeps reasoning start/end as bare markers", () => {
    expect(
      privatizeChunk({ type: "reasoning-start", id: "r1", providerMetadata: { a: 1 } }, s),
    ).toEqual({ type: "reasoning-start", id: "r1" });
  });

  it("drops activity data parts and scrubs status labels", () => {
    expect(privatizeChunk({ type: "data-digichatActivity", data: { tool: "x" } }, s)).toBeNull();
    expect(
      privatizeChunk(
        { type: "data-status", data: { status: "tool", label: "Searching Deskly", tool: "t" } },
        s,
      ),
    ).toEqual({
      type: "data-status",
      data: { status: "tool", label: `Searching ${PRIVATE_TERM_LABEL}` },
    });
    expect(privatizeChunk({ type: "data-notice", data: { text: "x" } }, s)).not.toBeNull();
  });
});

describe("privatizeChatResponse", () => {
  const turn = [
    { type: "start", messageId: "m1" },
    { type: "reasoning-start", id: "r1" },
    { type: "reasoning-delta", id: "r1", delta: "User is Jane Doe from Client Co" },
    { type: "reasoning-end", id: "r1" },
    { type: "tool-input-start", toolCallId: "c1", toolName: "deskly_search_tickets" },
    { type: "tool-input-delta", toolCallId: "c1", inputTextDelta: '{"q":"Jane' },
    {
      type: "tool-input-available",
      toolCallId: "c1",
      toolName: "deskly_search_tickets",
      input: { q: "Jane Doe" },
    },
    {
      type: "tool-output-available",
      toolCallId: "c1",
      output: { requester: "Jane Doe", email: "jane.doe@client.example" },
    },
    { type: "text-start", id: "t1" },
    { type: "text-delta", id: "t1", delta: "Write to jane.do" },
    { type: "text-delta", id: "t1", delta: "e@client.example via Deskly" },
    { type: "text-end", id: "t1" },
    { type: "finish" },
    "[DONE]",
  ];

  it("strips work payloads and scrubs the answer, end to end over SSE", async () => {
    const res = privatizeChatResponse(
      new Response(streamOf(sse(turn)), {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
      ["deskly"],
    );
    const raw = await res.clone().text();
    expect(raw).not.toContain("Jane");
    expect(raw).not.toContain("jane");
    expect(raw).not.toContain("Client Co");
    expect(raw.toLowerCase()).not.toContain("deskly");

    const events = await readEvents(res);
    // Text deltas are re-chunked at word boundaries; count the run once.
    const types = events
      .map((e) => (typeof e === "string" ? e : e.type))
      .filter((type, i, all) => type !== "text-delta" || all[i - 1] !== "text-delta");
    expect(types).toEqual([
      "start",
      "reasoning-start",
      "reasoning-delta",
      "reasoning-end",
      "tool-input-start",
      "tool-input-available",
      "tool-output-available",
      "text-start",
      "text-delta",
      "text-end",
      "finish",
      "[DONE]",
    ]);
    const text = events
      .filter((e): e is Record<string, unknown> => typeof e !== "string" && e.type === "text-delta")
      .map((e) => e.delta)
      .join("");
    expect(text).toBe(`Write to contact1@example.com via ${PRIVATE_TERM_LABEL}`);
    const reasoning = events.filter(
      (e): e is Record<string, unknown> => typeof e !== "string" && e.type === "reasoning-delta",
    );
    expect(reasoning).toEqual([{ type: "reasoning-delta", id: "r1", delta: PRIVATE_REASONING_TEXT }]);
  });

  it("flushes held-back text when the stream ends without text-end", async () => {
    const res = privatizeChatResponse(
      new Response(
        streamOf(sse([{ type: "text-start", id: "t" }, { type: "text-delta", id: "t", delta: "hi there" }])),
        { headers: { "content-type": "text/event-stream" } },
      ),
    );
    const events = await readEvents(res);
    expect(
      events
        .filter((e): e is Record<string, unknown> => typeof e !== "string" && e.type === "text-delta")
        .map((e) => e.delta)
        .join(""),
    ).toBe("hi there");
  });

  it("passes JSON responses through untouched", async () => {
    const original = new Response(JSON.stringify({ error: "x", email: "a@b.co" }), {
      status: 429,
      headers: { "content-type": "application/json" },
    });
    const res = privatizeChatResponse(original);
    expect(res).toBe(original);
  });
});
