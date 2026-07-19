import { describe, it, expect } from "vitest";
import type { UIMessage } from "ai";
import {
  mapFoundryEvent,
  createFoundryStreamResponse,
  type OpenAIResponsesClientLike,
  type FoundryStreamEvent,
} from "./foundry-stream";

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
      type: "trace",
      label: "Searching knowledge base…",
      status: "in_progress",
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
    ).toEqual({ type: "trace", label: 'Searched for: "auth flow"', status: "completed" });
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
    ).toEqual({ type: "trace", label: "Sources: auth.md", status: "completed" });
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
      type: "trace",
      label: "Sources: Authentication, https://datatap.stream/docs/no-title",
      status: "completed",
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
        openAIClientFactory: () => client,
      })
    );
    expect(out).toContain("agent unavailable");
  });
});
