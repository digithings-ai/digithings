import { describe, it, expect } from "vitest";
import type { UIMessage } from "ai";
import {
  mapFoundryEvent,
  createFoundryStreamResponse,
  type OpenAIResponsesClientLike,
  type FoundryStreamEvent,
} from "./foundry-stream";
import { toDigiChatActivity, type ActivitySpan } from "./chat-activity";

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
});
