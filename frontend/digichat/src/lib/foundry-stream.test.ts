import { describe, it, expect, vi, afterEach } from "vitest";
import type { UIMessage } from "ai";
import {
  mapFoundryEvent,
  createFoundryStreamResponse,
  FoundryToolLeakFilter,
  stripFoundryCitationMarkers,
  type OpenAIResponsesClientLike,
  type FoundryStreamEvent,
} from "./foundry-stream";
import { toDigiChatActivity, type ActivitySpan } from "./chat-activity";

afterEach(() => vi.restoreAllMocks());

describe("FoundryToolLeakFilter", () => {
  it("drops the fragmented remote_functions.azure_ai_search tool leak", () => {
    const filter = new FoundryToolLeakFilter();
    const parts = ["(remote", "_functions", ".azure", "_ai", "_search", ")"];
    expect(parts.map((p) => filter.push(p))).toEqual([null, null, null, null, null, null]);
  });

  it("passes through normal answer text", () => {
    const filter = new FoundryToolLeakFilter();
    expect(filter.push("Send ")).toBe("Send ");
    expect(filter.push("the key")).toBe("the key");
  });

  it("strips Foundry citation markers from a delta", () => {
    expect(stripFoundryCitationMarkers("key.【9:0†source】")).toBe("key.");
    const filter = new FoundryToolLeakFilter();
    expect(filter.push("X-API-KEY【6:2†source】")).toBe("X-API-KEY");
  });
});

function userMessage(text: string): UIMessage {
  return { id: "u1", role: "user", parts: [{ type: "text", text }] } as UIMessage;
}

async function drain(res: Response): Promise<string> {
  return await new Response(res.body).text();
}

function fakeClient(
  events: FoundryStreamEvent[],
  conversationId = "conv_9"
): { client: OpenAIResponsesClientLike; createSpy: { calls: unknown[][] } } {
  const createSpy: { calls: unknown[][] } = { calls: [] };
  const client: OpenAIResponsesClientLike = {
    conversations: {
      async create() {
        return { id: conversationId };
      },
    },
    responses: {
      async create(params, options) {
        createSpy.calls.push([params, options]);
        return {
          async *[Symbol.asyncIterator]() {
            for (const event of events) yield event;
          },
        };
      },
    },
  };
  return { client, createSpy };
}

describe("mapFoundryEvent", () => {
  it("maps a text delta event", () => {
    expect(mapFoundryEvent({ type: "response.output_text.delta", delta: "Hi" })).toEqual({
      type: "text-delta",
      delta: "Hi",
    });
  });

  it("emits the searching trace on in_progress only, not on the duplicate .searching event", () => {
    expect(mapFoundryEvent({ type: "response.file_search_call.in_progress" })).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "file_search",
        status: "started",
        label: "Searching knowledge base…",
      },
    });
    expect(mapFoundryEvent({ type: "response.file_search_call.searching" })).toBeNull();
  });

  it("ignores the terminal output_text.done re-emit that duplicated answers", () => {
    expect(mapFoundryEvent({ type: "response.output_text.done", text: "Hi there" })).toBeNull();
  });

  it("maps completion and error events", () => {
    expect(mapFoundryEvent({ type: "response.completed" })).toEqual({ type: "done" });
    expect(mapFoundryEvent({ type: "response.error", message: "boom" })).toEqual({
      type: "error",
      message: "boom",
    });
  });

  it("maps a completed file-search output item to a trace with the search queries", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: { type: "file_search_call", queries: ["auth flow"] },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "file_search",
        status: "completed",
        query: "auth flow",
        label: 'Searched for: "auth flow"',
      },
    });
  });

  it("maps a completed message output item with citations to a sources trace", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: {
          type: "message",
          content: [{ annotations: [{ filename: "auth.md" }, { filename: "auth.md" }] }],
        },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "retrieve",
        toolName: "file_search",
        status: "completed",
        label: "Sources",
        documents: [{ title: "auth.md", path: "auth.md" }],
      },
    });
  });

  it("maps url_citation annotations (azure_ai_search tool) to a sources trace, title over url", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: {
          type: "message",
          content: [
            {
              annotations: [
                { type: "url_citation", url: "https://datatap.stream/docs/auth", title: "Authentication" },
                { type: "url_citation", url: "https://datatap.stream/docs/auth", title: "Authentication" },
                { type: "url_citation", url: "https://datatap.stream/docs/no-title" },
              ],
            },
          ],
        },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "retrieve",
        toolName: "file_search",
        status: "completed",
        label: "Sources",
        documents: [
          { title: "Authentication", path: "https://datatap.stream/docs/auth" },
          {
            title: "https://datatap.stream/docs/no-title",
            path: "https://datatap.stream/docs/no-title",
          },
        ],
      },
    });
  });

  it("drops opaque azure_ai_search citations (doc_N + search.windows.net) — no body to show", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: {
          type: "message",
          content: [
            {
              annotations: [
                {
                  type: "url_citation",
                  url: "https://dg-search-datatap-web.search.windows.net/",
                  title: "doc_0",
                },
                {
                  type: "url_citation",
                  url: "https://dg-search-datatap-web.search.windows.net/",
                  title: "doc_3",
                },
              ],
            },
          ],
        },
      }),
    ).toBeNull();
  });

  it("returns null for unrecognized event types", () => {
    expect(mapFoundryEvent({ type: "response.output_item.added" })).toBeNull();
  });
});

describe("createFoundryStreamResponse", () => {
  it("creates a conversation and translates Foundry events into UI message stream parts", async () => {
    const { client, createSpy } = fakeClient([
      { type: "response.file_search_call.in_progress" },
      { type: "response.file_search_call.searching" },
      { type: "response.output_text.delta", delta: "Hel" },
      { type: "response.output_text.delta", delta: "lo" },
      { type: "response.output_text.done", text: "Hello" },
      { type: "response.completed" },
    ]);

    const res = await createFoundryStreamResponse({
      projectEndpoint: "https://proj.example.com",
      agentName: "digichat",
      messages: [userMessage("hello?")],
      conversationId: null,
      responseHeaders: { "X-Request-Id": "rid-1" },
      activityDetail: "full",
      openAIClientFactory: () => client,
    });
    const out = await drain(res);

    expect(out).toContain('"type":"data-externalConversation"');
    expect(out).toContain('"conversationId":"conv_9"');
    // exactly one searching trace, not two (dedup fix)
    expect(out.split("Searching knowledge base…").length - 1).toBe(1);
    expect(out).toContain('"delta":"Hel"');
    expect(out).toContain('"delta":"lo"');
    // the .done full-text re-emit must not appear as a delta (dup-answer fix)
    expect(out).not.toContain('"delta":"Hello"');
    expect(res.headers.get("X-Request-Id")).toBe("rid-1");

    expect(createSpy.calls[0][1]).toMatchObject({
      body: { agent_reference: { name: "digichat", type: "agent_reference" } },
    });
  });

  it("reuses a supplied conversationId instead of creating a new one", async () => {
    const { client, createSpy } = fakeClient([{ type: "response.completed" }]);
    await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "digichat",
        messages: [userMessage("again")],
        conversationId: "conv_existing",
        responseHeaders: {},
        activityDetail: "full",
        openAIClientFactory: () => client,
      })
    );
    expect(createSpy.calls[0][0]).toMatchObject({ conversation: "conv_existing", input: "again" });
  });

  it("surfaces a Foundry error event as a stream error part", async () => {
    const { client } = fakeClient([{ type: "response.error", message: "agent unavailable" }]);
    const out = await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "digichat",
        messages: [userMessage("q")],
        conversationId: null,
        responseHeaders: {},
        activityDetail: "full",
        openAIClientFactory: () => client,
      })
    );
    expect(out).toContain("agent unavailable");
  });

  // Distinct from the case above: this is an unexpected SDK/network exception
  // (e.g. auth failure, DNS error), not a response.error event Foundry meant
  // to be shown. It can carry stack traces or internal hostnames, and this
  // response reaches anonymous embed visitors — it must never reach the wire.
  it("masks a raw SDK/network exception instead of streaming its message", async () => {
    const client: OpenAIResponsesClientLike = {
      conversations: {
        async create() {
          return { id: "conv_x" };
        },
      },
      responses: {
        async create() {
          throw new Error("ECONNREFUSED 10.0.0.5:443 internal-foundry.corp");
        },
      },
    };
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});

    const out = await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "digichat",
        messages: [userMessage("q")],
        conversationId: null,
        responseHeaders: {},
        activityDetail: "full",
        openAIClientFactory: () => client,
      })
    );

    expect(out).not.toContain("ECONNREFUSED");
    expect(out).not.toContain("internal-foundry.corp");
    expect(out).toMatch(/unavailable|try again/i);
    expect(errorLog).toHaveBeenCalled();
  });
});

describe("mapFoundryEvent activity spans", () => {
  it("opens the search as a started execute_tool span", () => {
    expect(mapFoundryEvent({ type: "response.file_search_call.in_progress" })).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "file_search",
        status: "started",
        label: "Searching knowledge base…",
      },
    });
  });

  it("carries the real query on the completed search span", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: { type: "file_search_call", queries: ["how does auth work"] },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "file_search",
        status: "completed",
        query: "how does auth work",
        label: 'Searched for: "how does auth work"',
      },
    });
  });

  // azure_ai_search grounding: {type:"url_citation", url, title}. See 91caa0e0.
  it("maps url_citation annotations to retrieved documents", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: {
          type: "message",
          content: [
            {
              annotations: [
                { type: "url_citation", url: "https://x/auth", title: "Auth guide" },
                { type: "url_citation", url: "https://x/keys" },
              ],
            },
          ],
        },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "retrieve",
        toolName: "file_search",
        status: "completed",
        label: "Sources",
        documents: [
          { title: "Auth guide", path: "https://x/auth" },
          { title: "https://x/keys", path: "https://x/keys" },
        ],
      },
    });
  });

  // Foundry's native file_search grounding: {filename}, no url at all.
  it("maps filename annotations to retrieved documents", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: { type: "message", content: [{ annotations: [{ filename: "auth.md" }] }] },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "retrieve",
        toolName: "file_search",
        status: "completed",
        label: "Sources",
        documents: [{ title: "auth.md", path: "auth.md" }],
      },
    });
  });

  it("emits nothing for a message with no annotations", () => {
    expect(
      mapFoundryEvent({ type: "response.output_item.done", item: { type: "message", content: [] } })
    ).toBeNull();
  });
});

describe("createFoundryStreamResponse activity detail", () => {
  const searchEvents: FoundryStreamEvent[] = [
    { type: "response.file_search_call.in_progress" },
    {
      type: "response.output_item.done",
      item: {
        type: "message",
        content: [{ annotations: [{ type: "url_citation", url: "https://x/a", title: "A" }] }],
      },
    },
    { type: "response.output_text.delta", delta: "done" },
    { type: "response.completed" },
  ];

  async function run(activityDetail: "off" | "labels" | "full"): Promise<string> {
    const { client } = fakeClient(searchEvents);
    const res = await createFoundryStreamResponse({
      projectEndpoint: "https://p",
      agentName: "agent",
      messages: [userMessage("hi")],
      conversationId: "conv_1",
      responseHeaders: {},
      activityDetail,
      openAIClientFactory: () => client,
    });
    return await drain(res);
  }

  it("streams documents at full", async () => {
    const body = await run("full");
    expect(body).toContain("data-digichatActivity");
    expect(body).toContain("https://x/a");
  });

  // Foundry builds its span literal directly from upstream annotations rather
  // than going through the digigraph/relay chatActivitySpan helper, so it
  // needs its own enforcement of the same server-side caps — otherwise an
  // upstream response with many citations ships all of them over the wire
  // before the client ever gets a chance to truncate at render.
  it("caps an oversized citation list to MAX_DOCUMENTS before it reaches the stream", async () => {
    const manyAnnotations = Array.from({ length: 20 }, (_, i) => ({
      type: "url_citation" as const,
      url: `https://x/doc-${i}`,
      title: `Doc ${i}`,
    }));
    const { client } = fakeClient([
      {
        type: "response.output_item.done",
        item: { type: "message", content: [{ annotations: manyAnnotations }] },
      },
      { type: "response.completed" },
    ]);

    const body = await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://p",
        agentName: "agent",
        messages: [userMessage("hi")],
        conversationId: "conv_1",
        responseHeaders: {},
        activityDetail: "full",
        openAIClientFactory: () => client,
      })
    );

    expect(body).toContain("https://x/doc-0");
    expect(body).toContain("https://x/doc-7");
    expect(body).not.toContain("https://x/doc-8");
    expect(body).not.toContain("https://x/doc-19");
  });

  // The gate is server-side: a labels tenant must not receive the titles at all.
  it("withholds documents at labels", async () => {
    const body = await run("labels");
    expect(body).toContain("data-digichatActivity");
    expect(body).not.toContain("https://x/a");
  });

  it("emits no activity parts at off", async () => {
    const body = await run("off");
    expect(body).not.toContain("data-digichatActivity");
    expect(body).toContain("done");
  });

  // Regression: this exact fixture — file_search_call.in_progress (a "started"
  // execute_tool span with no query) followed by a message with url_citation
  // annotations and NO intervening file_search_call output_item.done — used to
  // produce a phantom, never-settling tool_call row alongside the tool_result
  // (chat-activity.ts's retrieve branch never consulted pendingRow). Only
  // asserting on raw stream bytes, as the tests above do, missed that: the
  // projected rows are what the UI actually renders, so assert those directly.
  it("projects this fixture to a single settled tool_result, not an orphaned tool_call", () => {
    const spans = searchEvents
      .map((event) => mapFoundryEvent(event))
      .filter((mapped): mapped is { type: "activity"; span: ActivitySpan } => mapped?.type === "activity")
      .map((mapped) => mapped.span);

    const rows = toDigiChatActivity(spans);

    expect(rows).toEqual([
      {
        kind: "tool_result",
        name: "file_search",
        query: "",
        hits: [{ title: "A", path: "https://x/a" }],
        count: 1,
      },
    ]);
  });

  // Progressive azure_ai_search: `.added` → running row; `.done` fills the
  // query without settling to "no hits"; output `.done` populates hits.
  // The session shows a bare flash caret under the chain — no Working… label.
  it("keeps azure_ai_search progressive across added → done → output", () => {
    const progressive: FoundryStreamEvent[] = [
      {
        type: "response.output_item.added",
        item: { type: "azure_ai_search_call", arguments: "" },
      },
      {
        type: "response.output_item.done",
        item: {
          type: "azure_ai_search_call",
          status: "completed",
          arguments: JSON.stringify({ query: "auth config" }),
        },
      },
      {
        type: "response.output_item.done",
        item: {
          type: "azure_ai_search_call_output",
          status: "completed",
          output: JSON.stringify({
            documents: [{ id: "chunk-1", content: "Auth lives in /api/config." }],
          }),
        },
      },
    ];

    const spans = progressive
      .map((event) => mapFoundryEvent(event))
      .filter((mapped): mapped is { type: "activity"; span: ActivitySpan } => mapped?.type === "activity")
      .map((mapped) => mapped.span);

    expect(toDigiChatActivity(spans.slice(0, 1), { settle: false })).toEqual([
      { kind: "tool_call", name: "azure_ai_search", query: "" },
    ]);

    expect(toDigiChatActivity(spans.slice(0, 2), { settle: false })).toEqual([
      { kind: "tool_call", name: "azure_ai_search", query: "auth config" },
    ]);

    expect(toDigiChatActivity(spans, { settle: false })).toMatchObject([
      {
        kind: "tool_result",
        name: "azure_ai_search",
        query: "auth config",
        count: 1,
      },
    ]);
  });
});
