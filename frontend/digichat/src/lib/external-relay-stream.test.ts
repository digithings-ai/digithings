import { describe, it, expect, afterEach, vi } from "vitest";
import type { UIMessage } from "ai";
import {
  parseRelaySse,
  lastUserMessageText,
  createExternalRelayStreamResponse,
} from "./external-relay-stream";

function sseBody(frames: string[], chunkSize = 7): ReadableStream<Uint8Array> {
  // Deliberately re-chunk across frame boundaries to prove buffering works.
  const whole = frames.join("");
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (let i = 0; i < whole.length; i += chunkSize) {
        controller.enqueue(encoder.encode(whole.slice(i, i + chunkSize)));
      }
      controller.close();
    },
  });
}

function userMessage(text: string): UIMessage {
  return { id: "u1", role: "user", parts: [{ type: "text", text }] } as UIMessage;
}

async function drain(res: Response): Promise<string> {
  return await new Response(res.body).text();
}

afterEach(() => vi.unstubAllGlobals());

describe("parseRelaySse", () => {
  it("yields typed events across chunk boundaries and skips malformed frames", async () => {
    const body = sseBody([
      'event: conversation\ndata: {"type":"conversation","conversationId":"c1"}\n\n',
      "event: junk\ndata: {not json}\n\n",
      'event: text-delta\ndata: {"type":"text-delta","delta":"Hi"}\n\n',
    ]);
    const events = [];
    for await (const e of parseRelaySse(body)) events.push(e);
    expect(events).toEqual([
      { event: "conversation", data: { type: "conversation", conversationId: "c1" } },
      { event: "text-delta", data: { type: "text-delta", delta: "Hi" } },
    ]);
  });
});

describe("lastUserMessageText", () => {
  it("returns the latest user message's joined text parts", () => {
    const messages = [
      userMessage("first"),
      { id: "a1", role: "assistant", parts: [{ type: "text", text: "reply" }] } as UIMessage,
      userMessage("second question"),
    ];
    expect(lastUserMessageText(messages)).toBe("second question");
  });
});

describe("createExternalRelayStreamResponse", () => {
  it("translates relay events into UI message stream parts", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        sseBody([
          'event: conversation\ndata: {"type":"conversation","conversationId":"conv_9"}\n\n',
          'event: trace\ndata: {"type":"trace","label":"Searching…","status":"in_progress"}\n\n',
          'event: text-delta\ndata: {"type":"text-delta","delta":"Hel"}\n\n',
          'event: text-delta\ndata: {"type":"text-delta","delta":"lo"}\n\n',
          'event: done\ndata: {"type":"done"}\n\n',
        ]),
        { status: 200 }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const res = await createExternalRelayStreamResponse({
      relayUrl: "https://relay.example.com/api/digichat",
      messages: [userMessage("hello?")],
      conversationId: null,
      responseHeaders: { "X-Request-Id": "rid-1" },
    });
    const out = await drain(res);

    expect(fetchMock).toHaveBeenCalledWith(
      "https://relay.example.com/api/digichat",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ conversationId: null, message: "hello?" }),
      })
    );
    expect(out).toContain('"type":"data-externalConversation"');
    expect(out).toContain('"conversationId":"conv_9"');
    expect(out).toContain('"type":"data-digigraphTrace"');
    expect(out).toContain('"external_activity"');
    expect(out).toContain('"delta":"Hel"');
    expect(out).toContain('"delta":"lo"');
    expect(res.headers.get("X-Request-Id")).toBe("rid-1");
  });

  it("drops the relay's terminal full-text re-emit so the answer is not duplicated", async () => {
    // The Foundry relay streams incremental deltas, then re-sends the COMPLETE
    // text as one terminal delta (verified against the live relay). That last
    // frame must be dropped, not forwarded.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          sseBody([
            'event: text-delta\ndata: {"type":"text-delta","delta":"Hi "}\n\n',
            'event: text-delta\ndata: {"type":"text-delta","delta":"there"}\n\n',
            'event: text-delta\ndata: {"type":"text-delta","delta":"Hi there"}\n\n',
            'event: done\ndata: {"type":"done"}\n\n',
          ]),
          { status: 200 }
        )
      )
    );
    const out = await drain(
      await createExternalRelayStreamResponse({
        relayUrl: "https://relay.example.com/api/digichat",
        messages: [userMessage("hi")],
        conversationId: null,
        responseHeaders: {},
      })
    );
    expect(out).toContain('"delta":"Hi "');
    expect(out).toContain('"delta":"there"');
    // the terminal snapshot equal to the whole answer so far is dropped
    expect(out).not.toContain('"delta":"Hi there"');
  });

  it("keeps a delta that equals the accumulated text when it is NOT the terminal frame", async () => {
    // Regression (#1434): the old guard dropped any delta equal to the text so
    // far, even mid-stream — so a legitimately doubled chunk ("xyz" then "xyz"
    // for "xyzxyz") lost content. The suppression must fire only on the actual
    // terminal re-emit (the delta immediately before `done`), not on any
    // equality with accumulated text.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          sseBody([
            'event: text-delta\ndata: {"type":"text-delta","delta":"xyz"}\n\n',
            'event: text-delta\ndata: {"type":"text-delta","delta":"xyz"}\n\n',
            'event: text-delta\ndata: {"type":"text-delta","delta":"!"}\n\n',
            'event: done\ndata: {"type":"done"}\n\n',
          ]),
          { status: 200 }
        )
      )
    );
    const out = await drain(
      await createExternalRelayStreamResponse({
        relayUrl: "https://relay.example.com/api/digichat",
        messages: [userMessage("hi")],
        conversationId: null,
        responseHeaders: {},
      })
    );
    // Both "xyz" deltas must be forwarded — count, since .toContain can't tell
    // one occurrence from two. The old code emitted it only once.
    const xyzCount = out.split('"delta":"xyz"').length - 1;
    expect(xyzCount).toBe(2);
    expect(out).toContain('"delta":"!"');
  });

  it("forwards the stored conversationId on subsequent turns", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(sseBody(['event: done\ndata: {"type":"done"}\n\n']), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);
    await (
      await createExternalRelayStreamResponse({
        relayUrl: "https://relay.example.com/api/digichat",
        messages: [userMessage("again")],
        conversationId: "conv_9",
        responseHeaders: {},
      })
    ).body?.cancel();
    expect(fetchMock.mock.calls[0][1].body).toBe(
      JSON.stringify({ conversationId: "conv_9", message: "again" })
    );
  });

  it("surfaces a relay error event as a stream error part", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          sseBody(['event: error\ndata: {"type":"error","message":"agent unavailable"}\n\n']),
          { status: 200 }
        )
      )
    );
    const out = await drain(
      await createExternalRelayStreamResponse({
        relayUrl: "https://relay.example.com/api/digichat",
        messages: [userMessage("q")],
        conversationId: null,
        responseHeaders: {},
      })
    );
    expect(out).toContain("agent unavailable");
    expect(out).toContain('"type":"error"');
  });

  it("reports a non-200 relay response as readable text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("boom", { status: 503, statusText: "Service Unavailable" }))
    );
    const out = await drain(
      await createExternalRelayStreamResponse({
        relayUrl: "https://relay.example.com/api/digichat",
        messages: [userMessage("q")],
        conversationId: null,
        responseHeaders: {},
      })
    );
    expect(out).toContain("Upstream error: 503");
  });
});
