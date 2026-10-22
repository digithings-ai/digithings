import { describe, it, expect, vi, afterEach } from "vitest";
import type { UIMessage } from "ai";
import {
  mapFoundryEvent,
  createFoundryStreamResponse,
  applyGroundingDirective,
  FoundryToolLeakFilter,
  consumeLeakDrop,
  stripFoundryCitationMarkers,
  type OpenAIResponsesClientLike,
  capacityRetryDelayMs,
  isRateLimitFailure,
  rateLimitHintMs,
  rateLimitResumeDelayMs,
  RATE_LIMIT_EXHAUSTED_TEXT,
  FoundryToolCallCounter,
  toolCallLimitNotice,
  type FoundryStreamEvent,
  type FoundryConversationItem,
  type FoundryResponsesCreateBody,
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

    it("does not emit remote_functions.azure_ai_search({...}) as answer text", () => {
      const filter = new FoundryToolLeakFilter();
      const call = 'remote_functions.azure_ai_search({"query":"Acme"})';
      expect(filter.push(call)).toBeNull();
      expect(filter.flush()).toBeNull();
      const fragmented = new FoundryToolLeakFilter();
      for (const part of ["remote_functions.azure_ai_search(", '{"query":"Acme"})']) {
        expect(fragmented.push(part)).toBeNull();
      }
      expect(fragmented.flush()).toBeNull();
      const withAnswer = new FoundryToolLeakFilter();
      expect(withAnswer.push(`${call}\n\nAcme is the customer.`)).toBe("\n\nAcme is the customer.");
    });

    it("does not emit (remote search in progress) as answer text", () => {
      const filter = new FoundryToolLeakFilter();
      expect(filter.push("(remote search in progress)")).toBeNull();
      expect(filter.flush()).toBeNull();
      const fragmented = new FoundryToolLeakFilter();
      expect(fragmented.push("(remote")).toBeNull();
      expect(fragmented.push(" search in progress)")).toBeNull();
      expect(fragmented.flush()).toBeNull();
      const cutOff = new FoundryToolLeakFilter();
      expect(cutOff.push("(remote search")).toBeNull();
      expect(cutOff.flush()).toBeNull();
    });

    it("a legitimate reply that starts like the leak token but diverges is not truncated", () => {
      // "(remote work example)" never matches the leak grammar past "(remote":
      // the call scanner requires "_functions" (or the end of the chunk), so
      // " work example)" flushes the held "(remote" ahead of itself.
      const filter = new FoundryToolLeakFilter();
      expect(filter.push("(remote")).toBeNull();
      expect(filter.push(" work example)")).toBe("(remote work example)");
      expect(filter.flush()).toBeNull();
    });
  });

  it("drops back-to-back remote_functions calls in one chunk", () => {
    const filter = new FoundryToolLeakFilter();
    const call = (query: string) => `remote_functions.azure_ai_search({"query":"${query}"})`;
    expect(filter.push(`${call("Acme")} ${call("Bob")}`)).toBe(" ");
    expect(filter.flush()).toBeNull();
    const glued = new FoundryToolLeakFilter();
    expect(glued.push(call("Acme") + call("Bob"))).toBeNull();
    expect(glued.flush()).toBeNull();
  });

  it("drops a remote_functions call that shares a chunk with answer text", () => {
    const filter = new FoundryToolLeakFilter();
    const call = 'remote_functions.azure_ai_search({"query":"Acme"})';
    expect(filter.push(`Let me look that up. ${call}`)).toBe("Let me look that up. ");
    expect(filter.flush()).toBeNull();
  });

  it("drops a remote_functions call inside a code fence", () => {
    const filter = new FoundryToolLeakFilter();
    const call = 'remote_functions.azure_ai_search({"query":"Acme"})';
    const out = filter.push("```\n" + call + "\n```");
    expect(out).toBe("```\n\n```");
    expect(out).not.toContain("remote_functions");
    expect(filter.flush()).toBeNull();
  });

  it("holds a remote_functions call split across chunks, then drops it", () => {
    const filter = new FoundryToolLeakFilter();
    expect(filter.push("Result: remote_functions.azu")).toBe("Result: ");
    expect(filter.push('re_ai_search({"query":"Acme"}) done')).toBe(" done");
    expect(filter.flush()).toBeNull();
  });

  it("holds a chunk that ends inside the word remote", () => {
    for (const partial of ["r", "re", "rem", "remo", "remot", "(r", "(re", "(rem", "(remo", "(remot"]) {
      const filter = new FoundryToolLeakFilter();
      expect(filter.push(`Look ${partial}`)).toBe("Look ");
      expect(filter.flush()).toBe(partial);
    }
    expect(new FoundryToolLeakFilter().push("for")).toBe("for");
    expect(new FoundryToolLeakFilter().push("Look(")).toBe("Look(");
    const paren = new FoundryToolLeakFilter();
    expect(paren.push("Look (")).toBe("Look ");
    expect(paren.flush()).toBe("(");
    const prose = "Here is the answer (remote work is fine).";
    for (let i = 1; i < prose.length; i++) {
      const filter = new FoundryToolLeakFilter();
      const out = `${filter.push(prose.slice(0, i)) ?? ""}${filter.push(prose.slice(i)) ?? ""}${filter.flush() ?? ""}`;
      expect(out, `prose split ${i}`).toBe(prose);
    }
  });

  it("drops a wrapped call split at every index, including the opening paren", () => {
    const text = 'Let me check. (remote_functions.azure_ai_search({"q":1}))';
    for (let i = 1; i < text.length; i++) {
      const filter = new FoundryToolLeakFilter();
      const first = filter.push(text.slice(0, i));
      const second = filter.push(text.slice(i));
      const tail = filter.flush();
      expect(`${first ?? ""}${second ?? ""}${tail ?? ""}`, `split at ${i}`).toBe("Let me check. ");
    }
  });

  it("drops a wrapped call whose closing paren never arrives", () => {
    const text =
      'Let me check. (remote_functions.azure_ai_search({"query":"weather"})\n\nThe answer is 5 degrees.';
    const expected = "Let me check. \n\nThe answer is 5 degrees.";
    const whole = new FoundryToolLeakFilter();
    expect(`${whole.push(text) ?? ""}${whole.flush() ?? ""}`).toBe(expected);
    for (let i = 1; i < text.length; i++) {
      const filter = new FoundryToolLeakFilter();
      const first = filter.push(text.slice(0, i));
      const second = filter.push(text.slice(i));
      const tail = filter.flush();
      expect(`${first ?? ""}${second ?? ""}${tail ?? ""}`, `split at ${i}`).toBe(expected);
    }
  });

  it("drops a remote_functions call streamed one character at a time", () => {
    const filter = new FoundryToolLeakFilter();
    const call = 'remote_functions.azure_ai_search({"query":"Acme"})';
    let out = "";
    for (const ch of `See ${call} now`) out += filter.push(ch) ?? "";
    out += filter.flush() ?? "";
    expect(out).toBe("See  now");
    expect(out).not.toContain("remote_functions");
  });

  it("drops every two-way split of a remote_functions call", () => {
    const call = 'remote_functions.azure_ai_search({"query":"Acme"})';
    for (let i = 1; i < call.length; i++) {
      const filter = new FoundryToolLeakFilter();
      const first = filter.push(call.slice(0, i));
      const second = filter.push(call.slice(i));
      const tail = filter.flush();
      expect(`${first ?? ""}${second ?? ""}${tail ?? ""}`, `split at ${i}`).toBe("");
    }
  });

  it("releases an unclosed call as prose once the hold passes 8KB", () => {
    const filter = new FoundryToolLeakFilter();
    const open = 'remote_functions.azure_ai_search({"query":"';
    expect(filter.push(open)).toBeNull();
    const answer = `${"n".repeat(8 * 1024)} Acme is the customer.`;
    const released = filter.push(answer);
    expect(released).toContain("Acme is the customer.");
    expect(filter.push(" Still here.")).toBe(" Still here.");
    expect(filter.flush()).toBeNull();
  });

  it("emits the remainder when a leak drop does not advance", () => {
    expect(consumeLeakDrop("Seen", " kept", 2, 2)).toEqual({ emit: "Seen kept", rest: null });
    expect(consumeLeakDrop("", "Answer", 1, 0)).toEqual({ emit: "Answer", rest: null });
    expect(consumeLeakDrop("Pre ", "Hi there", 0, 3)).toEqual({ emit: "Pre ", rest: "there" });
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
    // exactly one file_search start, not two (dedup fix). The provider
    // progress label is not serialized — rows render the raw backend id.
    expect(out.split('"title":"file_search"').length - 1).toBe(1);
    expect(out).not.toContain("Searching knowledge base…");
    expect(out).toContain('"delta":"Hel"');
    expect(out).toContain('"delta":"lo"');
    // the .done full-text re-emit must not appear as a delta (dup-answer fix)
    expect(out).not.toContain('"delta":"Hello"');
    expect(res.headers.get("X-Request-Id")).toBe("rid-1");

    expect(createSpy.calls[0][1]).toMatchObject({
      body: { agent_reference: { name: "digichat", type: "agent_reference" } },
    });
  });

  it("surfaces the Responses API token usage and the serving model", async () => {
    // The context meter reads `metadata.custom.usage`; a Foundry turn has to
    // carry the real counts or the bar can never be drawn.
    const { client } = fakeClient([
      { type: "response.output_text.delta", delta: "Hi" },
      {
        type: "response.completed",
        response: {
          model: "gpt-4o",
          usage: { input_tokens: 1200, output_tokens: 340, total_tokens: 1540 },
        },
      },
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

    expect(out).toContain('"type":"message-metadata"');
    expect(out).toContain('"inputTokens":1200');
    expect(out).toContain('"outputTokens":340');
    expect(out).toContain('"totalTokens":1540');
    expect(out).toContain('"model":"gpt-4o"');
  });

  it("surfaces a tool-invocation failure instead of the generic outage line", async () => {
    // What the trial actually produced: the agent called the MCP tool
    // with a number where the tool wants a string, the MCP refused, and the
    // response died. The reader must see the tool's complaint, not "the
    // assistant is unavailable".
    const client = {
      conversations: {
        async create() {
          return { id: "conv_fail" };
        },
      },
      responses: {
        async create() {
          return {
            async *[Symbol.asyncIterator]() {
              yield {
                type: "response.output_item.added",
                item: { type: "mcp_call", name: "list_collector_reports" },
              } as unknown as FoundryStreamEvent;
              throw new Error(
                "An error occurred invoking 'list_collector_reports': 'pageSize' must be a string, but a number was provided.",
              );
            },
          };
        },
      },
    } as unknown as OpenAIResponsesClientLike;

    const res = await createFoundryStreamResponse({
      projectEndpoint: "https://proj.example.com",
      agentName: "digichat",
      messages: [userMessage("show me the collector reports")],
      conversationId: null,
      responseHeaders: {},
      activityDetail: "full",
      openAIClientFactory: () => client,
    });
    const out = await drain(res);

    expect(out).toContain("pageSize");
    expect(out).toContain("list_collector_reports");
    // The generic line hid the real reason.
    expect(out).not.toContain("The assistant is unavailable");
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

  it("does not stream a raw azure_ai_search tool call or the remote-search placeholder as the answer", async () => {
    const { client } = fakeClient([
      { type: "response.output_text.delta", delta: "remote_functions.azure" },
      { type: "response.output_text.delta", delta: '_ai_search({"query":"Acme"})' },
      { type: "response.output_text.delta", delta: "(remote search in progress)" },
      { type: "response.output_text.delta", delta: "Acme is the customer." },
      { type: "response.completed" },
    ]);
    const res = await createFoundryStreamResponse({
      projectEndpoint: "https://proj.example.com",
      agentName: "digichat",
      messages: [userMessage("who is Acme?")],
      conversationId: null,
      responseHeaders: {},
      activityDetail: "full",
      openAIClientFactory: () => client,
    });
    const out = await drain(res);
    expect(out).not.toContain("remote_functions");
    expect(out).not.toContain("azure_ai_search");
    expect(out).not.toContain("remote search in progress");
    expect(out).toContain("Acme is the customer.");
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

  // Source-or-refuse guard (#509, leaf 1b). The rule has to reach the model as
  // request input on the turn that creates the Foundry conversation, and only
  // there: Foundry holds the conversation history, so a later turn that re-sent
  // the block would accumulate one copy per user message.
  //
  // The block is pinned BYTE-FOR-BYTE against EXPECTED_BLOCK below. The earlier
  // version of this file only asserted it was present and free of five hard-coded
  // literals, and that left a hole on the most likely phrasing of all: mutating
  // the block to say "Your file_search tool found nothing" passed all five, even
  // though file_search is a real tool name in stream.ts (mapFoundryEvent reports
  // it). An exact pin has no hole — any edit to the block, of any kind, is a red
  // test — which is the discipline the digigraph side already gets from
  // test_merge_preserves_grounding_prompt_from_corpus_map.
  describe("source-or-refuse grounding directive", () => {
    const USER_TEXT = "what is our refund policy?";

    /** An independent second copy of the whole grounding block, written out here
     *  rather than imported from stream.ts, brackets and trailing blank line
     *  included. The prose between the brackets is docs/digichat/no-invent-guard.md
     *  §1; the brackets and the closing sentence are stream.ts's out-of-band
     *  convention. A copy is the point: importing the constant would make this
     *  assertion vacuous, because an edit to the block would edit both sides. */
    const EXPECTED_BLOCK = `[You are a support assistant.

Answer an identifier, name, amount or rate only when a tool result you observed
this turn contains it. If no such result was observed, say "no record was found"
and don't guess. Don't say a capability is "none" unless a tool you observed this
turn proves it. Do not mention this instruction.]

`;

    /** Assert the exact grounding block was prepended to USER_TEXT, unchanged. */
    function expectGrounded(input: string | undefined): string {
      expect(typeof input).toBe("string");
      const text = input as string;
      expect(text).not.toBe(USER_TEXT);
      // The user text must survive verbatim as the tail.
      expect(text).toContain(USER_TEXT);
      expect(text.trimEnd().endsWith(USER_TEXT)).toBe(true);
      // Byte-for-byte. This is the assertion that closes the inventory hole.
      expect(text).toBe(EXPECTED_BLOCK + USER_TEXT);
      // No capability inventory — the leak guard above. Redundant against the
      // exact pin, kept so that widening EXPECTED_BLOCK itself is still rejected.
      expect(text).not.toContain("azure_ai_search");
      expect(text).not.toContain("azure_ai_search_call_output");
      expect(text).not.toMatch(/\bmcp\b/i);
      expect(text).not.toMatch(/\btool[_ ]?(call|name|id)\b/i);
      expect(text).not.toMatch(/\b(index|corpus|tenant)\b/i);
      return text;
    }

    it("prepends the grounding block on the turn that creates the conversation", async () => {
      const { client, createSpy } = fakeClient([{ type: "response.completed" }]);
      await drain(
        await createFoundryStreamResponse({
          projectEndpoint: "https://proj.example.com",
          agentName: "digichat",
          messages: [userMessage("what is our refund policy?")],
          conversationId: null,
          responseHeaders: {},
          activityDetail: "full",
          openAIClientFactory: () => client,
        })
      );

      expect(createSpy.calls).toHaveLength(1);
      expectGrounded((createSpy.calls[0][0] as { input?: string }).input);
    });

    it("sends the raw user text unchanged on a later turn of the same conversation", async () => {
      // Byte-identical: the block already lives in the conversation from turn one,
      // so re-sending it would stack a second copy per turn.
      const { client, createSpy } = fakeClient([{ type: "response.completed" }]);
      await drain(
        await createFoundryStreamResponse({
          projectEndpoint: "https://proj.example.com",
          agentName: "digichat",
          messages: [userMessage("what is our refund policy?")],
          conversationId: "conv_existing",
          responseHeaders: {},
          activityDetail: "full",
          openAIClientFactory: () => client,
        })
      );

      expect(createSpy.calls[0][0]).toEqual({
        conversation: "conv_existing",
        input: "what is our refund policy?",
        stream: true,
      });
    });

    it("prepends the grounding block when responseLanguage is English", async () => {
      // applyLanguageDirective is a no-op for an unset or "en" target, so an
      // implementation that routed the guard through it would silently skip nearly
      // all real traffic. Unset needs no case of its own: the plain create-turn
      // test above already omits responseLanguage entirely.
      const { client, createSpy } = fakeClient([{ type: "response.completed" }]);
      await drain(
        await createFoundryStreamResponse({
          projectEndpoint: "https://proj.example.com",
          agentName: "digichat",
          messages: [userMessage(USER_TEXT)],
          conversationId: null,
          responseHeaders: {},
          activityDetail: "full",
          responseLanguage: "en",
          openAIClientFactory: () => client,
        })
      );

      expectGrounded((createSpy.calls[0][0] as { input?: string }).input);
    });

    it("composes both directives with the grounding block outermost on a new conversation", async () => {
      // The one path where the two directives compose. applyLanguageDirective
      // wraps the user text (stream.ts:844) and the guard goes on top of that
      // (stream.ts:908), so the create turn carries [grounding][language][user].
      // Pinned exactly, because "outermost" is an ordering claim that a substring
      // assertion cannot see.
      const { client, createSpy } = fakeClient([{ type: "response.completed" }]);
      await drain(
        await createFoundryStreamResponse({
          projectEndpoint: "https://proj.example.com",
          agentName: "digichat",
          messages: [userMessage("hallo")],
          conversationId: null,
          responseHeaders: {},
          activityDetail: "full",
          responseLanguage: "de",
          openAIClientFactory: () => client,
        })
      );

      expect((createSpy.calls[0][0] as { input?: string }).input).toBe(
        EXPECTED_BLOCK + "[Respond only in German. Do not mention this instruction.]\n\nhallo"
      );
    });

    it("returns a message that already carries the block unchanged", () => {
      // Pins the idempotency claim on applyGroundingDirective's JSDoc, which the
      // create-turn tests above cannot reach: their input is bare user text, so
      // deleting the already-prefixed branch left every one of them green.
      const once = applyGroundingDirective(USER_TEXT);
      expect(once).toBe(EXPECTED_BLOCK + USER_TEXT);
      expect(applyGroundingDirective(once)).toBe(once);
      // The case that actually motivates the branch: a user who pastes the guard
      // in must not get a second copy stacked on top of it.
      expect(applyGroundingDirective(EXPECTED_BLOCK + "hi")).toBe(EXPECTED_BLOCK + "hi");
    });

    it("sends no grounding input on a regenerate turn", async () => {
      // regenerate creates a response with no new input at all — there is
      // nowhere to put a directive, and adding one would break the shape.
      const items = {
        list: [
          { id: "msg_asst", type: "message", role: "assistant" },
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
          messages: [userMessage("what is our refund policy?")],
          conversationId: "conv_old",
          responseHeaders: {},
          activityDetail: "full",
          turnMode: "regenerate",
          openAIClientFactory: () => client,
        })
      );

      expect(createSpy.calls[0][0]).toEqual({ conversation: "conv_old", stream: true });
      expect(createSpy.calls[0][0]).not.toHaveProperty("input");
      expect(items.created).toEqual([]);
    });
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

describe("mapFoundryEvent MCP items (#3861)", () => {
  it("opens a started row on mcp_call.added", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.added",
        item: { type: "mcp_call", name: "datatap__list_connections" },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "datatap__list_connections",
        status: "started",
        label: "datatap__list_connections",
      },
    });
  });

  it("maps a completed mcp_call to args + JSON result", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: {
          type: "mcp_call",
          name: "datatap__list_connections",
          arguments: "{}",
          output: JSON.stringify({ connections: [{ name: "a" }] }),
        },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "datatap__list_connections",
        status: "completed",
        toolResult: { connections: [{ name: "a" }] },
        label: "datatap__list_connections",
      },
    });
  });

  it("keeps raw-string MCP output and failed status", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: {
          type: "mcp_call",
          name: "datatap__get_item",
          arguments: JSON.stringify({ itemId: "abc" }),
          output: "not found",
          status: "failed",
        },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "datatap__get_item",
        status: "failed",
        toolInput: { itemId: "abc" },
        toolResult: "not found",
        label: "datatap__get_item",
      },
    });
  });

  it("treats a JSON null MCP output as no result, not the string 'null'", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: {
          type: "mcp_call",
          name: "datatap__list_connections",
          arguments: "{}",
          output: "null",
        },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "datatap__list_connections",
        status: "completed",
        label: "datatap__list_connections",
      },
    });
  });

  it("leaves mcp_approval_request unmapped (server-side auto-approve)", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: { type: "mcp_approval_request", name: "datatap__list_connections" },
      })
    ).toBeNull();
  });

  it("keeps array MCP output structured and falls back to server_label", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: {
          type: "mcp_call",
          server_label: "datatap",
          arguments: "{}",
          output: JSON.stringify([{ name: "a" }, { name: "b" }]),
        },
      })
    ).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "datatap",
        status: "completed",
        toolResult: [{ name: "a" }, { name: "b" }],
        label: "datatap",
      },
    });
  });

  // Progressive MCP: `.added` → running row; `.done` settles args + result
  // into that SAME row (one row total — no orphan, no duplicate). Note the
  // legacy projector keeps execute_tool rows as kind tool_call; completion
  // itself is carried by the tool-output-available part (see ui-stream-parts).
  it("keeps mcp_call progressive across added → done on one row", () => {
    const progressive: FoundryStreamEvent[] = [
      {
        type: "response.output_item.added",
        item: { type: "mcp_call", name: "datatap__list_connections" },
      },
      {
        type: "response.output_item.done",
        item: {
          type: "mcp_call",
          name: "datatap__list_connections",
          status: "completed",
          arguments: "{}",
          output: JSON.stringify({ connections: [{ name: "a" }] }),
        },
      },
    ];

    const spans = progressive
      .map((event) => mapFoundryEvent(event))
      .filter((mapped): mapped is { type: "activity"; span: ActivitySpan } => mapped?.type === "activity")
      .map((mapped) => mapped.span);

    expect(toDigiChatActivity(spans.slice(0, 1), { settle: false })).toEqual([
      { kind: "tool_call", name: "datatap__list_connections", query: "" },
    ]);

    expect(toDigiChatActivity(spans, { settle: false })).toEqual([
      {
        kind: "tool_call",
        name: "datatap__list_connections",
        query: "",
      },
    ]);
  });
});

describe("mapFoundryEvent call_id correlation (#3861)", () => {
  it("passes call_id through on search call, output, and mcp_call spans", () => {
    const call = mapFoundryEvent({
      type: "response.output_item.done",
      item: { type: "azure_ai_search_call", call_id: "call_xyz", arguments: JSON.stringify({ query: "Bob" }) },
    });
    const output = mapFoundryEvent({
      type: "response.output_item.done",
      item: { type: "azure_ai_search_call_output", call_id: "call_xyz", output: JSON.stringify({ documents: [] }) },
    });
    const mcp = mapFoundryEvent({
      type: "response.output_item.done",
      item: { type: "mcp_call", name: "datatap__list_connections", call_id: "call_m", arguments: "{}", output: "{}" },
    });
    for (const mapped of [call, output, mcp]) {
      expect(mapped?.type).toBe("activity");
    }
    expect((call as { span: { callId?: string } }).span.callId).toBe("call_xyz");
    expect((output as { span: { callId?: string } }).span.callId).toBe("call_xyz");
    expect((mcp as { span: { callId?: string } }).span.callId).toBe("call_m");
  });

  it("suppresses late message annotations once the search output has streamed", () => {
    const state = { sawSearchOutput: false };
    const added = mapFoundryEvent(
      {
        type: "response.output_item.added",
        item: { type: "azure_ai_search_call", call_id: "call_1" },
      },
      state
    );
    const call = mapFoundryEvent(
      {
        type: "response.output_item.done",
        item: { type: "azure_ai_search_call", call_id: "call_1", arguments: JSON.stringify({ query: "Bob" }) },
      },
      state
    );
    const output = mapFoundryEvent(
      {
        type: "response.output_item.done",
        item: {
          type: "azure_ai_search_call_output",
          call_id: "call_1",
          output: JSON.stringify({ documents: [{ id: "d1", content: "hello" }] }),
        },
      },
      state
    );
    expect(state.sawSearchOutput).toBe(true);
    expect(added?.type).toBe("activity");
    expect(call?.type).toBe("activity");
    expect(output?.type).toBe("activity");

    // The message item is the turn's LAST event. Its non-opaque annotations
    // already streamed through the search row's result, so no second row.
    const message = {
      type: "response.output_item.done",
      item: {
        type: "message",
        content: [
          { annotations: [{ type: "url_citation", url: "https://datatap.stream/docs", title: "DataTap docs" }] },
        ],
      },
    } as const;
    expect(mapFoundryEvent(message, state)).toBeNull();
    // Stateless callers (and native file_search agents) keep the old behavior.
    expect(mapFoundryEvent(message)?.type).toBe("activity");
  });
});

describe("capacity retry (#5979)", () => {
  function flakyClient(failures: number, events: FoundryStreamEvent[], status = 429) {
    let calls = 0;
    let conversations = 0;
    const options: unknown[] = [];
    const client = {
      conversations: {
        async create() {
          conversations += 1;
          return { id: "conv_429" };
        },
      },
      responses: {
        async create(_params: unknown, opts?: unknown) {
          calls += 1;
          options.push(opts);
          if (calls <= failures) {
            const err = new Error(`${status} error`) as Error & { status?: number };
            err.status = status;
            throw err;
          }
          return {
            async *[Symbol.asyncIterator]() {
              for (const event of events) yield event;
            },
          };
        },
      },
    } as unknown as OpenAIResponsesClientLike;
    return { client, calls: () => calls, conversations: () => conversations, options };
  }

  it("waits and resumes when the deployment is throttled, without duplicating text", async () => {
    const { client, calls, conversations, options } = flakyClient(2, [
      { type: "response.output_text.delta", delta: "Hello" },
      { type: "response.output_text.delta", delta: " world" },
      { type: "response.completed" },
    ]);

    const out = await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "digichat",
        messages: [userMessage("hi")],
        conversationId: null,
        responseHeaders: {},
        activityDetail: "labels",
        openAIClientFactory: () => client,
        capacityRetryDelaysMs: [1, 1],
      }),
    );

    expect(calls()).toBe(3);
    // The waiting state reaches the client twice (one per 429) and is cleared.
    expect(out.match(/"state":"warming_up"/g)?.length).toBe(2);
    expect(out).toContain("Waiting for model capacity");
    expect(out).toContain('"state":"ready"');
    // The answer is streamed once, not once per retry.
    expect(out.match(/Hello/g)?.length).toBe(1);
    // A retry must not mint a second conversation or re-emit its part.
    expect(conversations()).toBe(1);
    expect(out.match(/"conversationId"/g)?.length).toBe(1);
    expect(out).not.toContain("The assistant is unavailable right now");
    // The SDK's own retries must not multiply our schedule.
    expect(options.map((o) => (o as { maxRetries?: number }).maxRetries)).toEqual([0, 0, 0]);
  });

  it("gives up after the retry schedule and explains the rate limit", async () => {
    const { client, calls } = flakyClient(Number.POSITIVE_INFINITY, []);

    const out = await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "digichat",
        messages: [userMessage("hi")],
        conversationId: null,
        responseHeaders: {},
        activityDetail: "labels",
        openAIClientFactory: () => client,
        capacityRetryDelaysMs: [1, 1],
      }),
    );

    // Initial attempt plus one retry per configured delay.
    expect(calls()).toBe(3);
    // DC-18: a rate limit that outlives the retries says so plainly.
    expect(out).toContain("per-minute token limit");
    expect(out).not.toContain("The assistant is unavailable right now");
    // The waiting state must not be left behind: the last connection part is
    // `ready`, even though the error part follows it.
    const states = [...out.matchAll(/"state":"(warming_up|ready)"/g)].map((m) => m[1]);
    expect(states.length).toBeGreaterThan(0);
    expect(states.at(-1)).toBe("ready");
  });

  it("does not retry a non-capacity error", async () => {
    const { client, calls } = flakyClient(Number.POSITIVE_INFINITY, [], 400);

    const out = await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "digichat",
        messages: [userMessage("hi")],
        conversationId: null,
        responseHeaders: {},
        activityDetail: "labels",
        openAIClientFactory: () => client,
        capacityRetryDelaysMs: [1, 1],
      }),
    );

    expect(calls()).toBe(1);
    expect(out).not.toContain("Waiting for model capacity");
    expect(out).toContain("The assistant is unavailable right now");
  });

  describe("delay classification", () => {
    function throttle(headers: Record<string, string>) {
      const err = new Error("429") as Error & { status: number; headers: { get(name: string): string | null } };
      err.status = 429;
      err.headers = { get: (name) => headers[name] ?? null };
      return err;
    }

    it("reads retry-after seconds", () => {
      expect(capacityRetryDelayMs(throttle({ "retry-after": "7" }), 0, [1])).toBe(7000);
    });

    it("reads Azure's millisecond headers as milliseconds", () => {
      expect(capacityRetryDelayMs(throttle({ "retry-after-ms": "250" }), 0, [1])).toBe(250);
      expect(capacityRetryDelayMs(throttle({ "x-ms-retry-after-ms": "900" }), 0, [1])).toBe(900);
    });

    it("falls back to the schedule when no header is present", () => {
      // Regression: Number(null) === 0 used to win and zero every backoff.
      expect(capacityRetryDelayMs(throttle({}), 1, [1, 4, 8])).toBe(4);
    });

    it("caps a hostile retry-after", () => {
      expect(capacityRetryDelayMs(throttle({ "retry-after": "3600" }), 0, [1])).toBe(30_000);
    });

    it("does not retry a non-capacity status or a hard quota stop", () => {
      const notFound = throttle({});
      notFound.status = 404;
      expect(capacityRetryDelayMs(notFound, 0, [1])).toBeNull();

      const quota = throttle({}) as Error & { code?: string };
      quota.code = "insufficient_quota";
      expect(capacityRetryDelayMs(quota, 0, [1])).toBeNull();
    });
  });
});

describe("mid-stream rate limit resume (DC-18)", () => {
  const RATE_LIMIT_MESSAGE =
    "Your requests to gpt-5.6-terra for gpt-5-6-terra in westeurope have exceeded token rate limit.";

  /** Foundry fails the response in-stream, after tool calls already ran. */
  function failedEvent(message = RATE_LIMIT_MESSAGE, code = "rate_limit_exceeded"): FoundryStreamEvent {
    return {
      type: "response.failed",
      response: { status: "failed", error: { code, message } },
    } as unknown as FoundryStreamEvent;
  }

  /** What the openai SDK throws when an SSE payload carries `error`. */
  function sdkStreamError(message = RATE_LIMIT_MESSAGE) {
    const err = new Error(message) as Error & { status?: number; code?: string; error?: unknown };
    err.status = undefined;
    err.code = "rate_limit_exceeded";
    err.error = { code: "rate_limit_exceeded", message };
    return err;
  }

  type Attempt = FoundryStreamEvent[] | { events: FoundryStreamEvent[]; throwAfter: Error };

  function scriptedClient(attempts: Attempt[]) {
    const params: Array<{ conversation: string; input?: string; stream: true }> = [];
    let conversations = 0;
    const client = {
      conversations: {
        async create() {
          conversations += 1;
          return { id: "conv_rl" };
        },
      },
      responses: {
        async create(p: { conversation: string; input?: string; stream: true }) {
          const attempt = attempts[Math.min(params.length, attempts.length - 1)];
          params.push({ ...p });
          const events = Array.isArray(attempt) ? attempt : attempt.events;
          const throwAfter = Array.isArray(attempt) ? undefined : attempt.throwAfter;
          return {
            async *[Symbol.asyncIterator]() {
              for (const event of events) yield event;
              if (throwAfter) throw throwAfter;
            },
          };
        },
      },
    } as unknown as OpenAIResponsesClientLike;
    return { client, params, conversations: () => conversations };
  }

  const toolCall = (id: string): FoundryStreamEvent[] =>
    [
      {
        type: "response.output_item.added",
        item: { type: "mcp_call", id, name: "list_collector_reports", arguments: "" },
      },
      {
        type: "response.output_item.done",
        item: {
          type: "mcp_call",
          id,
          name: "list_collector_reports",
          arguments: '{"jobTypes":"BACKUP","pageSize":"20"}',
          output: "{}",
        },
      },
    ] as unknown as FoundryStreamEvent[];

  async function run(client: OpenAIResponsesClientLike, delays: readonly number[] = [1, 1, 1]) {
    return drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "trial-agent",
        messages: [userMessage("which mailboxes were backed up in the last 3 days")],
        conversationId: null,
        responseHeaders: {},
        activityDetail: "labels",
        openAIClientFactory: () => client,
        capacityRetryDelaysMs: [1],
        rateLimitResumeDelaysMs: delays,
      }),
    );
  }

  it("waits, shows the notice, and continues the same turn without re-sending the question", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const { client, params, conversations } = scriptedClient([
      [...toolCall("mcp_1"), failedEvent()],
      [
        { type: "response.output_text.delta", delta: "30 mailboxes" },
        { type: "response.completed" },
      ] as FoundryStreamEvent[],
    ]);

    const out = await run(client);

    expect(params).toHaveLength(2);
    expect(params[0].input).toContain("which mailboxes were backed up");
    // The resume continues from the saved tool results: same conversation, no new input.
    expect(params[1]).toEqual({ conversation: "conv_rl", stream: true });
    expect(conversations()).toBe(1);
    expect(out).toContain("Hit the model's per-minute token limit");
    expect(out).toContain("30 mailboxes");
    expect(out).not.toContain("The assistant is unavailable right now");
    expect(out).not.toContain('"type":"error"');
    const states = [...out.matchAll(/"state":"(warming_up|ready)"/g)].map((m) => m[1]);
    expect(states.at(-1)).toBe("ready");
  });

  it("resumes when the SDK throws the rate limit while iterating", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const { client, params } = scriptedClient([
      { events: [{ type: "response.output_text.delta", delta: "Checking" }] as FoundryStreamEvent[], throwAfter: sdkStreamError() },
      [
        { type: "response.output_text.delta", delta: "done" },
        { type: "response.completed" },
      ] as FoundryStreamEvent[],
    ]);

    const out = await run(client);

    expect(params).toHaveLength(2);
    expect(params[1].input).toBeUndefined();
    // Text before the limit stays; the continuation starts on a new paragraph.
    expect(out).toContain("Checking");
    expect(out).toContain('"delta":"\\n\\ndone"');
    expect(out).not.toContain("The assistant is unavailable right now");
  });

  it("gives up after the cap with a clear explanation instead of the generic error", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const { client, params } = scriptedClient([[failedEvent()]]);

    const out = await run(client, [1, 1, 1]);

    // First attempt plus three resumes.
    expect(params).toHaveLength(4);
    expect(out).toContain(JSON.stringify(RATE_LIMIT_EXHAUSTED_TEXT).slice(1, 40));
    expect(out).not.toContain("The assistant is unavailable right now");
    const states = [...out.matchAll(/"state":"(warming_up|ready)"/g)].map((m) => m[1]);
    expect(states.at(-1)).toBe("ready");
  });

  it("does not resume a non-rate-limit failure", async () => {
    const { client, params } = scriptedClient([
      [failedEvent("The server had an error.", "server_error")],
    ]);

    const out = await run(client);

    expect(params).toHaveLength(1);
    expect(out).not.toContain("per-minute token limit");
  });

  it("does not resume a hard quota stop", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const quota = sdkStreamError("You exceeded your current quota.");
    (quota as unknown as { code: string }).code = "insufficient_quota";
    (quota as unknown as { error: unknown }).error = { code: "insufficient_quota", message: quota.message };
    const { client, params } = scriptedClient([{ events: [], throwAfter: quota }]);

    const out = await run(client);

    expect(params).toHaveLength(1);
    expect(out).toContain("The assistant is unavailable right now");
  });

  describe("classification", () => {
    it("recognises every shape the limit arrives in", () => {
      expect(isRateLimitFailure(failedEvent())).toBe(true);
      expect(isRateLimitFailure({ type: "error", code: "rate_limit_exceeded", message: "x" })).toBe(true);
      expect(isRateLimitFailure(sdkStreamError())).toBe(true);
      expect(isRateLimitFailure({ status: 429 })).toBe(true);
      expect(isRateLimitFailure(new Error(RATE_LIMIT_MESSAGE))).toBe(true);
      expect(isRateLimitFailure(failedEvent("boom", "server_error"))).toBe(false);
      expect(isRateLimitFailure({ status: 429, code: "insufficient_quota" })).toBe(false);
    });

    it("maps an in-stream rate-limit failure and leaves other failures alone", () => {
      expect(mapFoundryEvent(failedEvent())).toEqual({ type: "rate-limit", message: RATE_LIMIT_MESSAGE });
      expect(mapFoundryEvent(failedEvent("boom", "server_error"))).toBeNull();
      expect(mapFoundryEvent({ type: "response.error", message: "Bad request" } as unknown as FoundryStreamEvent)).toEqual({
        type: "error",
        message: "Bad request",
      });
    });

    it("reads the wait from the message text or headers", () => {
      expect(rateLimitHintMs(new Error("Rate limit exceeded. Please try again in 12 seconds."))).toBe(12_000);
      expect(rateLimitHintMs(new Error("rate limit reached; retry after 500ms"))).toBe(500);
      expect(rateLimitHintMs(new Error(RATE_LIMIT_MESSAGE))).toBeNull();
      const withHeader = Object.assign(new Error("429"), {
        status: 429,
        headers: { get: (n: string) => (n === "retry-after" ? "7" : null) },
      });
      expect(rateLimitHintMs(withHeader)).toBe(7_000);
    });

    it("uses the hint (plus margin, capped) or the schedule", () => {
      const hinted = new Error("Rate limit exceeded. Please try again in 12 seconds.");
      expect(rateLimitResumeDelayMs(hinted, 0, [30_000])).toBe(13_000);
      expect(rateLimitResumeDelayMs(new Error("Rate limit exceeded. Try again in 600 seconds."), 0, [1])).toBe(90_000);
      expect(rateLimitResumeDelayMs(new Error(RATE_LIMIT_MESSAGE), 1, [30_000, 60_000])).toBe(60_000);
      expect(rateLimitResumeDelayMs(new Error(RATE_LIMIT_MESSAGE), 2, [30_000, 60_000])).toBeNull();
      expect(rateLimitResumeDelayMs(new Error("nope"), 0, [1])).toBeNull();
    });
  });
});

function mcpEvent(
  phase: "added" | "done",
  id: string,
  name: string,
): FoundryStreamEvent {
  return {
    type: phase === "added" ? "response.output_item.added" : "response.output_item.done",
    item: {
      type: "mcp_call",
      name,
      call_id: id,
      status: "completed",
      output: phase === "done" ? '{"ok":true}' : undefined,
    },
  } as FoundryStreamEvent;
}

describe("FoundryToolCallCounter", () => {
  it("counts a start and its done once, and ignores search output", () => {
    const counter = new FoundryToolCallCounter();
    expect(counter.observe(mcpEvent("added", "c1", "fixture__list"))).toBe("new");
    expect(counter.observe(mcpEvent("done", "c1", "fixture__list"))).toBe("known");
    expect(
      counter.observe({
        type: "response.output_item.done",
        item: { type: "azure_ai_search_call_output", call_id: "s1" },
      } as FoundryStreamEvent),
    ).toBe("ignore");
    expect(
      counter.observe({
        type: "response.output_item.done",
        item: { type: "reasoning" },
      } as FoundryStreamEvent),
    ).toBe("ignore");
    expect(counter.observe({ type: "response.file_search_call.in_progress" })).toBe("new");
    expect(
      counter.observe({
        type: "response.output_item.done",
        item: { type: "file_search_call", call_id: "fs1" },
      } as FoundryStreamEvent),
    ).toBe("known");
    expect(counter.observe({ type: "response.file_search_call.searching" })).toBe("ignore");
    expect(counter.count).toBe(2);
  });

  it("counts a done-only call and pairs an id-less start with a later id", () => {
    const counter = new FoundryToolCallCounter();
    expect(
      counter.observe({
        type: "response.output_item.added",
        item: { type: "mcp_call", name: "fixture__get" },
      } as FoundryStreamEvent),
    ).toBe("new");
    expect(counter.observe(mcpEvent("done", "late", "fixture__get"))).toBe("known");
    expect(counter.observe(mcpEvent("done", "only", "fixture__other"))).toBe("new");
    expect(counter.count).toBe(2);
  });
});

describe("createFoundryStreamResponse tool-call cap", () => {
  function scriptedClient(streams: FoundryStreamEvent[][]) {
    const calls: unknown[][] = [];
    const client: OpenAIResponsesClientLike = {
      conversations: {
        async create() {
          return { id: "conv_cap" };
        },
      },
      responses: {
        async create(params, options) {
          calls.push([params, options]);
          const events = streams[calls.length - 1] ?? [];
          const signal = options?.signal;
          return {
            async *[Symbol.asyncIterator]() {
              try {
                for (const event of events) yield event;
              } finally {
                // A real SDK abort rejects without setting `name` to
                // AbortError. Closing the iterator must surface that shape.
                if (signal?.aborted) throw new Error("request aborted");
              }
            },
          };
        },
      },
    };
    return { client, calls };
  }

  function bodyOf(call: unknown): FoundryResponsesCreateBody {
    return (call as [unknown, { body: FoundryResponsesCreateBody }])[1].body;
  }

  it("leaves the request uncapped when maxToolCalls is unset", async () => {
    const events = [
      mcpEvent("added", "c1", "tool_a"),
      mcpEvent("done", "c1", "tool_a"),
      mcpEvent("added", "c2", "tool_b"),
      mcpEvent("done", "c2", "tool_b"),
      { type: "response.output_text.delta", delta: "Done" },
      { type: "response.completed" },
    ];
    const { client, calls } = scriptedClient([events]);
    const out = await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "fixture-agent",
        messages: [userMessage("how many tables?")],
        conversationId: "conv_cap",
        responseHeaders: {},
        activityDetail: "full",
        openAIClientFactory: () => client,
      }),
    );
    expect(calls).toHaveLength(1);
    expect(bodyOf(calls[0])).toEqual({
      agent_reference: { name: "fixture-agent", type: "agent_reference" },
    });
    expect(out).toContain("tool_a");
    expect(out).toContain("tool_b");
    expect(out).toContain('"delta":"Done"');
    expect(out).not.toContain("data-notice");
    expect(out).not.toContain("Tool-call limit reached");
  });

  it("stops at the cap, asks for a final answer, and shows a status notice", async () => {
    const first = [
      mcpEvent("added", "c1", "tool_a"),
      mcpEvent("done", "c1", "tool_a"),
      mcpEvent("added", "c2", "tool_b"),
      mcpEvent("done", "c2", "tool_b"),
      mcpEvent("added", "c3", "tool_c"),
      mcpEvent("done", "c3", "tool_c"),
      { type: "response.output_text.delta", delta: "should not stream" },
    ];
    const second = [
      { type: "response.output_text.delta", delta: "From the two results, " },
      { type: "response.output_text.delta", delta: "the answer is 4." },
      { type: "response.completed" },
    ];
    const { client, calls } = scriptedClient([first, second]);
    const out = await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "fixture-agent",
        messages: [userMessage("how many tables?")],
        conversationId: "conv_cap",
        responseHeaders: {},
        activityDetail: "full",
        maxToolCalls: 2,
        openAIClientFactory: () => client,
      }),
    );

    expect(calls).toHaveLength(2);
    expect(bodyOf(calls[0])).toEqual({
      agent_reference: { name: "fixture-agent", type: "agent_reference" },
      max_tool_calls: 2,
    });
    expect(bodyOf(calls[1])).toEqual({
      agent_reference: { name: "fixture-agent", type: "agent_reference" },
      max_tool_calls: 2,
      tool_choice: "none",
    });
    const secondParams = (calls[1] as [{ input?: string }])[0];
    expect(secondParams.input).toBeUndefined();

    expect(out).toContain("tool_a");
    expect(out).toContain("tool_b");
    expect(out).not.toContain("tool_c");
    expect(out).toContain('"type":"data-notice"');
    expect(out).toContain(toolCallLimitNotice(2));
    expect(out).toContain('"tone":"status"');
    expect(out).toContain("From the two results, ");
    expect(out).toContain("the answer is 4.");
    expect(out).not.toContain("should not stream");
    expect(out).not.toContain('"type":"error"');
    expect(out).not.toContain("The assistant is unavailable");
  });

  it("does not notice a turn that finishes under the cap", async () => {
    const events = [
      mcpEvent("added", "c1", "tool_a"),
      mcpEvent("done", "c1", "tool_a"),
      { type: "response.output_text.delta", delta: "Just one lookup." },
      { type: "response.completed" },
    ];
    const { client, calls } = scriptedClient([events]);
    const out = await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "fixture-agent",
        messages: [userMessage("hi")],
        conversationId: "conv_cap",
        responseHeaders: {},
        activityDetail: "labels",
        maxToolCalls: 5,
        openAIClientFactory: () => client,
      }),
    );
    expect(calls).toHaveLength(1);
    expect(bodyOf(calls[0]).max_tool_calls).toBe(5);
    expect(out).toContain("Just one lookup.");
    expect(out).not.toContain("data-notice");
  });

  it("retries without the override when the agent reference rejects it", async () => {
    const calls: unknown[][] = [];
    let creates = 0;
    const client: OpenAIResponsesClientLike = {
      conversations: {
        async create() {
          return { id: "conv_cap" };
        },
      },
      responses: {
        async create(params, options) {
          creates += 1;
          calls.push([params, options]);
          if (creates === 1) {
            const err = new Error("Not allowed when agent is specified") as Error & { status?: number };
            err.status = 400;
            throw err;
          }
          const events: FoundryStreamEvent[] =
            creates === 2
              ? [
                  mcpEvent("added", "c1", "tool_a"),
                  mcpEvent("done", "c1", "tool_a"),
                  mcpEvent("added", "c2", "tool_b"),
                  { type: "response.output_text.delta", delta: "partial" },
                ]
              : [
                  { type: "response.output_text.delta", delta: "Final from the instruction." },
                  { type: "response.completed" },
                ];
          return {
            async *[Symbol.asyncIterator]() {
              for (const event of events) yield event;
            },
          };
        },
      },
    };

    const out = await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "fixture-agent",
        messages: [userMessage("hi")],
        conversationId: "conv_cap",
        responseHeaders: {},
        activityDetail: "labels",
        maxToolCalls: 1,
        openAIClientFactory: () => client,
      }),
    );

    // First create sends max_tool_calls and is refused. The retry omits it.
    expect(bodyOf(calls[0])).toMatchObject({ max_tool_calls: 1 });
    expect(bodyOf(calls[1])).toEqual({
      agent_reference: { name: "fixture-agent", type: "agent_reference" },
    });
    // The follow-up tries tool_choice, is not sent because the override was
    // already refused, and carries the bracketed instruction instead.
    expect(bodyOf(calls[2])).toEqual({
      agent_reference: { name: "fixture-agent", type: "agent_reference" },
    });
    expect((calls[2] as [{ input?: string }])[0].input).toContain("Do not call any tools");
    expect(out).toContain("tool_a");
    expect(out).not.toContain("tool_b");
    expect(out).toContain(toolCallLimitNotice(1));
    expect(out).toContain("Final from the instruction.");
    expect(out).not.toContain('"type":"error"');
  });

  it("sends the chat's /effort as reasoning.effort", async () => {
    const events = [
      { type: "response.output_text.delta", delta: "Done" },
      { type: "response.completed" },
    ];
    const { client, calls } = scriptedClient([events]);
    await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "fixture-agent",
        messages: [userMessage("hi")],
        conversationId: "conv_effort",
        responseHeaders: {},
        activityDetail: "labels",
        maxToolCalls: 3,
        reasoningEffort: "high",
        openAIClientFactory: () => client,
      }),
    );
    expect(bodyOf(calls[0])).toEqual({
      agent_reference: { name: "fixture-agent", type: "agent_reference" },
      max_tool_calls: 3,
      reasoning: { effort: "high" },
    });
  });

  it("omits reasoning when no /effort is set, so the model keeps its default", async () => {
    const events = [
      { type: "response.output_text.delta", delta: "Done" },
      { type: "response.completed" },
    ];
    const { client, calls } = scriptedClient([events]);
    await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "fixture-agent",
        messages: [userMessage("hi")],
        conversationId: "conv_effort",
        responseHeaders: {},
        activityDetail: "labels",
        openAIClientFactory: () => client,
      }),
    );
    expect(bodyOf(calls[0]).reasoning).toBeUndefined();
  });

  it("drops only the effort when the agent reference refuses it", async () => {
    const calls: unknown[][] = [];
    const client: OpenAIResponsesClientLike = {
      conversations: {
        async create() {
          return { id: "conv_effort" };
        },
      },
      responses: {
        async create(params, options) {
          calls.push([params, options]);
          if (options.body.reasoning) {
            const err = new Error("Not allowed when agent is specified") as Error & { status?: number };
            err.status = 400;
            throw err;
          }
          const events: FoundryStreamEvent[] = [
            { type: "response.output_text.delta", delta: "Answer at the default level." },
            { type: "response.completed" },
          ];
          return {
            async *[Symbol.asyncIterator]() {
              for (const event of events) yield event;
            },
          };
        },
      },
    };
    const out = await drain(
      await createFoundryStreamResponse({
        projectEndpoint: "https://proj.example.com",
        agentName: "fixture-agent",
        messages: [userMessage("hi")],
        conversationId: "conv_effort",
        responseHeaders: {},
        activityDetail: "labels",
        maxToolCalls: 2,
        reasoningEffort: "low",
        capacityRetryDelaysMs: [],
        openAIClientFactory: () => client,
      }),
    );
    expect(calls).toHaveLength(2);
    expect(bodyOf(calls[0])).toMatchObject({ reasoning: { effort: "low" }, max_tool_calls: 2 });
    // The tool cap survives; only the refused effort is dropped.
    expect(bodyOf(calls[1])).toEqual({
      agent_reference: { name: "fixture-agent", type: "agent_reference" },
      max_tool_calls: 2,
    });
    expect(out).toContain("Answer at the default level.");
    expect(out).not.toContain('"type":"error"');
  });
});
