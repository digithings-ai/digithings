import { describe, it, expect, vi, afterEach } from "vitest";
import type { UIMessage } from "ai";
import {
  mapFoundryEvent,
  createFoundryStreamResponse,
  FoundryToolLeakFilter,
  stripFoundryCitationMarkers,
  type OpenAIResponsesClientLike,
  type FoundryStreamEvent,
  type FoundryConversationItem,
} from "./stream";
import { toDigiChatActivity, MAX_DOCUMENTS, type ActivitySpan } from "@/lib/chat-activity";

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

  describe("flush", () => {
    it("returns null when nothing is buffered", () => {
      const filter = new FoundryToolLeakFilter();
      expect(filter.flush()).toBeNull();
      filter.push("ordinary text");
      expect(filter.flush()).toBeNull();
    });

    it("drains a held prefix the stream never disambiguated", () => {
      const filter = new FoundryToolLeakFilter();
      // Ends exactly on an incomplete leak-token prefix — push holds it and
      // never got a later delta to resolve it one way or the other.
      expect(filter.push("(remote")).toBeNull();
      expect(filter.flush()).toBe("(remote");
    });

    it("empties the buffer once flushed, so a second flush returns null", () => {
      const filter = new FoundryToolLeakFilter();
      filter.push("remote_functions.azure");
      filter.flush();
      expect(filter.flush()).toBeNull();
    });

    it("does not flush a completed leak token — push already discarded it", () => {
      const filter = new FoundryToolLeakFilter();
      for (const p of ["(remote", "_functions", ".azure", "_ai", "_search", ")"]) filter.push(p);
      expect(filter.flush()).toBeNull();
    });

    it("a legitimate reply that starts like the leak token but diverges is not truncated", () => {
      // "(remote work example)" never matches the leak grammar past "(remote" —
      // isRemoteFunctionsLeakPrefix requires the token to continue with
      // "_functions" (or close immediately), so " work example)" flushes the
      // held "(remote" ahead of itself. flush() at the end is a null-op here;
      // the real assertion is that push() already returned everything.
      const filter = new FoundryToolLeakFilter();
      expect(filter.push("(remote")).toBeNull();
      expect(filter.push(" work example)")).toBe("(remote work example)");
      expect(filter.flush()).toBeNull();
    });
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
  conversationId = "conv_9",
  opts?: {
    items?: {
      list: FoundryConversationItem[];
      deleted: string[];
      created: unknown[];
    };
  },
): { client: OpenAIResponsesClientLike; createSpy: { calls: unknown[][] } } {
  const createSpy: { calls: unknown[][] } = { calls: [] };
  const itemsState = opts?.items;
  const client: OpenAIResponsesClientLike = {
    conversations: {
      async create() {
        return { id: conversationId };
      },
      ...(itemsState
        ? {
            items: {
              async list() {
                return { data: itemsState.list };
              },
              async delete(itemId: string, params: { conversation_id: string }) {
                itemsState.deleted.push(`${params.conversation_id}:${itemId}`);
              },
              async create(_conversationId: string, body: unknown) {
                itemsState.created.push(body);
              },
            },
          }
        : {}),
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

// searchOutputDocuments/pickString/humanizeChunkId/isReadableSnippet are
// module-private — reached the same way production code reaches them, through
// an azure_ai_search_call_output output_item.done event.
describe("searchOutputDocuments (via mapFoundryEvent)", () => {
  function searchOutputEvent(documents: unknown[]): FoundryStreamEvent {
    return {
      type: "response.output_item.done",
      item: {
        type: "azure_ai_search_call_output",
        status: "completed",
        output: JSON.stringify({ documents }),
      },
    };
  }

  it("prefers title/url over the raw chunk id", () => {
    const mapped = mapFoundryEvent(
      searchOutputEvent([
        { id: "chunk-1", title: "Auth Config", url: "https://datatap.stream/docs/auth" },
      ]),
    );
    expect(mapped).toMatchObject({
      span: { documents: [{ title: "Auth Config", path: "https://datatap.stream/docs/auth" }] },
    });
  });

  it("falls back to SourceName/Url when title/url are absent", () => {
    const mapped = mapFoundryEvent(
      searchOutputEvent([
        { id: "chunk-2", SourceName: "Billing Guide", Url: "https://datatap.stream/docs/billing" },
      ]),
    );
    expect(mapped).toMatchObject({
      span: { documents: [{ title: "Billing Guide", path: "https://datatap.stream/docs/billing" }] },
    });
  });

  it("humanizes an OpenAPI chunk id when no title/url field resolves", () => {
    const mapped = mapFoundryEvent(
      searchOutputEvent([{ id: "openapi_public_GET__api_config__tenantId___chunk0" }]),
    );
    expect(mapped).toMatchObject({
      span: {
        documents: [{ title: "GET /api/config/tenantId", path: "openapi_public_GET__api_config__tenantId___chunk0" }],
      },
    });
  });

  it("humanizes a page chunk id when no title/url field resolves", () => {
    const mapped = mapFoundryEvent(searchOutputEvent([{ id: "page__docs__auth__chunk2" }]));
    expect(mapped).toMatchObject({
      span: { documents: [{ title: "docs/auth", path: "page__docs__auth__chunk2" }] },
    });
  });

  it("falls back to the raw id verbatim when it matches no known chunk-id shape", () => {
    const mapped = mapFoundryEvent(searchOutputEvent([{ id: "unrecognized-shape-42" }]));
    expect(mapped).toMatchObject({
      span: { documents: [{ title: "unrecognized-shape-42", path: "unrecognized-shape-42" }] },
    });
  });

  it("keeps a readable snippet", () => {
    const mapped = mapFoundryEvent(
      searchOutputEvent([{ id: "chunk-3", content: "Auth lives in /api/config." }]),
    );
    expect(mapped).toMatchObject({
      span: { documents: [{ snippet: "Auth lives in /api/config." }] },
    });
  });

  it("drops an HTML snippet", () => {
    const mapped = mapFoundryEvent(
      searchOutputEvent([{ id: "chunk-4", content: "<div>raw page markup</div>" }]),
    );
    const doc = (mapped as { span: { documents: Array<{ snippet?: string }> } }).span.documents[0];
    expect(doc.snippet).toBeUndefined();
  });

  it("drops a JSON-blob snippet", () => {
    const mapped = mapFoundryEvent(
      searchOutputEvent([{ id: "chunk-5", content: '{"openapi":"3.0.4","paths":{}}' }]),
    );
    const doc = (mapped as { span: { documents: Array<{ snippet?: string }> } }).span.documents[0];
    expect(doc.snippet).toBeUndefined();
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

    expect(out).toContain('"type":"data-conversation"');
    expect(out).not.toContain('"type":"data-externalConversation"');
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

  it("flushes a held leak-prefix instead of silently dropping the tail of a reply", async () => {
    // The final delta ends the stream exactly on an incomplete leak-token
    // prefix ("(remote") — nothing downstream ever disambiguates it, so
    // without the post-loop flush this text is dropped with no error.
    const { client } = fakeClient([
      { type: "response.output_text.delta", delta: "See the " },
      { type: "response.output_text.delta", delta: "(remote" },
      { type: "response.completed" },
    ]);

    const res = await createFoundryStreamResponse({
      projectEndpoint: "https://proj.example.com",
      agentName: "digichat",
      messages: [userMessage("hello?")],
      conversationId: null,
      responseHeaders: {},
      activityDetail: "full",
      openAIClientFactory: () => client,
    });
    const out = await drain(res);

    expect(out).toContain('"delta":"See the "');
    expect(out).toContain('"delta":"(remote"');
  });

  it("flushes a held leak-prefix when the stream exhausts naturally, not just on a done break", async () => {
    // Same risk as above, but the fake source ends by running out of events
    // rather than emitting response.completed — the for-await loop exits by
    // falling through, not via the `mapped.type === "done"` break. The flush
    // sits after the loop either way, but this proves it isn't accidentally
    // reachable only from the break arm.
    const { client } = fakeClient([
      { type: "response.output_text.delta", delta: "See the " },
      { type: "response.output_text.delta", delta: "(remote" },
    ]);

    const res = await createFoundryStreamResponse({
      projectEndpoint: "https://proj.example.com",
      agentName: "digichat",
      messages: [userMessage("hello?")],
      conversationId: null,
      responseHeaders: {},
      activityDetail: "full",
      openAIClientFactory: () => client,
    });
    const out = await drain(res);

    expect(out).toContain('"delta":"See the "');
    expect(out).toContain('"delta":"(remote"');
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

  it("regenerate deletes trailing assistant items and does not re-send user text", async () => {
    const items = {
      list: [
        { id: "msg_asst", type: "message", role: "assistant" },
        { id: "tool_1", type: "azure_ai_search_call" },
        { id: "msg_user", type: "message", role: "user" },
      ] satisfies FoundryConversationItem[],
      deleted: [] as string[],
      created: [] as unknown[],
    };
    const { client, createSpy } = fakeClient([{ type: "response.completed" }], "conv_old", {
      items,
    });
    await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "digichat",
        messages: [userMessage("same user text")],
        conversationId: "conv_old",
        responseHeaders: {},
        activityDetail: "full",
        openAIClientFactory: () => client,
        turnMode: "regenerate",
      }),
    );
    expect(items.deleted).toEqual(["conv_old:msg_asst", "conv_old:tool_1"]);
    expect(items.created).toEqual([]);
    expect(createSpy.calls[0][0]).toEqual({ conversation: "conv_old", stream: true });
    expect(createSpy.calls[0][0]).not.toHaveProperty("input");
  });

  it("edit_last_user deletes through the last user item then creates the edited text", async () => {
    const items = {
      list: [
        { id: "msg_asst", type: "message", role: "assistant" },
        { id: "msg_user", type: "message", role: "user" },
        { id: "msg_prior", type: "message", role: "assistant" },
      ] satisfies FoundryConversationItem[],
      deleted: [] as string[],
      created: [] as unknown[],
    };
    const { client, createSpy } = fakeClient([{ type: "response.completed" }], "conv_edit", {
      items,
    });
    await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "digichat",
        messages: [userMessage("edited question")],
        conversationId: "conv_edit",
        responseHeaders: {},
        activityDetail: "full",
        openAIClientFactory: () => client,
        turnMode: "edit_last_user",
      }),
    );
    expect(items.deleted).toEqual(["conv_edit:msg_asst", "conv_edit:msg_user"]);
    expect(items.created).toEqual([
      { items: [{ type: "message", role: "user", content: "edited question" }] },
    ]);
    expect(createSpy.calls[0][0]).toEqual({ conversation: "conv_edit", stream: true });
  });

  it("returns 501 when regenerate is requested without an item mutation API", async () => {
    const { client } = fakeClient([{ type: "response.completed" }]);
    const res = await createFoundryStreamResponse({
      projectEndpoint: "https://proj.example.com",
      agentName: "digichat",
      messages: [userMessage("q")],
      conversationId: "conv_old",
      responseHeaders: {},
      activityDetail: "full",
      openAIClientFactory: () => client,
      turnMode: "regenerate",
    });
    expect(res.status).toBe(501);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("not_supported");
  });

  it("prepends a language directive to input when responseLanguage is a non-English curated code", async () => {
    const { client, createSpy } = fakeClient([{ type: "response.completed" }]);
    await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "digichat",
        messages: [userMessage("hallo")],
        conversationId: "conv-1",
        responseHeaders: {},
        activityDetail: "labels",
        openAIClientFactory: () => client,
        responseLanguage: "de",
      })
    );
    expect(createSpy.calls[0][0]).toMatchObject({
      input: "[Respond only in German. Do not mention this instruction.]\n\nhallo",
    });
  });

  it("does not alter input when responseLanguage is English or unset", async () => {
    const { client, createSpy } = fakeClient([{ type: "response.completed" }]);
    await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "digichat",
        messages: [userMessage("hi")],
        conversationId: "conv-1",
        responseHeaders: {},
        activityDetail: "labels",
        openAIClientFactory: () => client,
      })
    );
    expect(createSpy.calls[0][0]).toMatchObject({ input: "hi" });
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
    expect(body).toContain("source-url");
    expect(body).toContain("https://x/a");
    expect(body).not.toContain("data-digichatActivity");
  });

  // Foundry builds its span literal directly from upstream annotations rather
  // than going through the digigraph/relay chatActivitySpan helper, so it
  // needs its own enforcement of the same server-side caps — otherwise an
  // upstream response with many citations ships all of them over the wire
  // before the client ever gets a chance to truncate at render.
  it("caps an oversized citation list to MAX_DOCUMENTS before it reaches the stream", async () => {
    const manyAnnotations = Array.from({ length: MAX_DOCUMENTS + 5 }, (_, i) => ({
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
    expect(body).toContain(`https://x/doc-${MAX_DOCUMENTS - 1}`);
    expect(body).not.toContain(`https://x/doc-${MAX_DOCUMENTS}`);
    expect(body).not.toContain(`https://x/doc-${MAX_DOCUMENTS + 4}`);
  });

  // The gate is server-side: a labels tenant must not receive the titles at all.
  it("withholds documents at labels", async () => {
    const body = await run("labels");
    expect(body).toContain("documentsWithheld");
    expect(body).not.toContain("https://x/a");
    expect(body).not.toContain("data-digichatActivity");
  });

  it("emits no activity parts at off", async () => {
    const body = await run("off");
    expect(body).not.toContain("data-digichatActivity");
    expect(body).not.toContain("tool-input-start");
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
