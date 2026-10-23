import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import {
  createFoundryStreamResponse,
  mapFoundryEvent,
  type FoundryMapState,
  type FoundryStreamEvent,
  type OpenAIResponsesClientLike,
} from "./stream";

// get_item display Fix A: Foundry can stream an MCP call's input on
// `response.mcp_call_arguments.delta` / `.done` and close the `mcp_call` item
// with `arguments` empty or "{}". The row then showed `{}`.
const ev = (e: Record<string, unknown>) => e as unknown as FoundryStreamEvent;

function doneItem(args: string | undefined) {
  return ev({
    type: "response.output_item.done",
    item: {
      type: "mcp_call",
      id: "mcp_1",
      name: "get_item",
      ...(args === undefined ? {} : { arguments: args }),
      output: '{"ok":true}',
    },
  });
}

describe("mcp_call arguments streamed separately (get_item Fix A)", () => {
  it("assembles .delta fragments into the done row's input when the item has none", () => {
    const state: FoundryMapState = { sawSearchOutput: false };
    expect(
      mapFoundryEvent(
        ev({ type: "response.mcp_call_arguments.delta", item_id: "mcp_1", delta: '{"uniqueKey":' }),
        state,
      ),
    ).toBeNull();
    expect(
      mapFoundryEvent(
        ev({ type: "response.mcp_call_arguments.delta", item_id: "mcp_1", delta: '"abc-123"}' }),
        state,
      ),
    ).toBeNull();
    const out = mapFoundryEvent(doneItem("{}"), state);
    expect(out).toMatchObject({
      type: "activity",
      span: { toolName: "get_item", status: "completed", toolInput: { uniqueKey: "abc-123" } },
    });
  });

  it("prefers the full .done arguments over the fragments", () => {
    const state: FoundryMapState = { sawSearchOutput: false };
    mapFoundryEvent(
      ev({ type: "response.mcp_call_arguments.delta", item_id: "mcp_1", delta: '{"uniq' }),
      state,
    );
    mapFoundryEvent(
      ev({
        type: "response.mcp_call_arguments.done",
        item_id: "mcp_1",
        arguments: '{"uniqueKey":"k-9"}',
      }),
      state,
    );
    const out = mapFoundryEvent(doneItem(""), state);
    expect(out).toMatchObject({ span: { toolInput: { uniqueKey: "k-9" } } });
  });

  it("keeps the item's own arguments when it carries them", () => {
    const state: FoundryMapState = { sawSearchOutput: false };
    mapFoundryEvent(
      ev({
        type: "response.mcp_call_arguments.done",
        item_id: "mcp_1",
        arguments: '{"uniqueKey":"streamed"}',
      }),
      state,
    );
    const out = mapFoundryEvent(doneItem('{"uniqueKey":"own"}'), state);
    expect(out).toMatchObject({ span: { toolInput: { uniqueKey: "own" } } });
  });

  it("does not borrow another item's arguments", () => {
    const state: FoundryMapState = { sawSearchOutput: false };
    mapFoundryEvent(
      ev({
        type: "response.mcp_call_arguments.done",
        item_id: "mcp_other",
        arguments: '{"uniqueKey":"x"}',
      }),
      state,
    );
    const out = mapFoundryEvent(doneItem(undefined), state);
    expect(out && "span" in out ? out.span.toolInput : "no-span").toBeUndefined();
  });

  it("ignores argument events without state or with malformed fields", () => {
    expect(
      mapFoundryEvent(
        ev({ type: "response.mcp_call_arguments.delta", item_id: "mcp_1", delta: "{}" }),
      ),
    ).toBeNull();
    const state: FoundryMapState = { sawSearchOutput: false };
    expect(
      mapFoundryEvent(
        ev({ type: "response.mcp_call_arguments.delta", item_id: 7, delta: "{}" }),
        state,
      ),
    ).toBeNull();
    expect(
      mapFoundryEvent(
        ev({ type: "response.mcp_call_arguments.done", item_id: "mcp_1", arguments: 3 }),
        state,
      ),
    ).toBeNull();
    expect(state.mcpArguments).toBeUndefined();
  });

  it("leaves a malformed streamed input out of the row instead of throwing", () => {
    const state: FoundryMapState = { sawSearchOutput: false };
    mapFoundryEvent(
      ev({ type: "response.mcp_call_arguments.delta", item_id: "mcp_1", delta: '{"uniqueKey":' }),
      state,
    );
    const out = mapFoundryEvent(doneItem("{}"), state);
    expect(out && "span" in out ? out.span.toolInput : "no-span").toBeUndefined();
  });

  it("keeps the fragments when .done carries an empty or {} arguments string", () => {
    for (const empty of ["", "{}"]) {
      const state: FoundryMapState = { sawSearchOutput: false };
      mapFoundryEvent(
        ev({
          type: "response.mcp_call_arguments.delta",
          item_id: "mcp_1",
          delta: '{"uniqueKey":"frag"}',
        }),
        state,
      );
      mapFoundryEvent(
        ev({ type: "response.mcp_call_arguments.done", item_id: "mcp_1", arguments: empty }),
        state,
      );
      const out = mapFoundryEvent(doneItem("{}"), state);
      expect(out, JSON.stringify(empty)).toMatchObject({
        span: { toolInput: { uniqueKey: "frag" } },
      });
    }
  });

  it("starts a new buffer when the same item streams again after .done", () => {
    const state: FoundryMapState = { sawSearchOutput: false };
    mapFoundryEvent(
      ev({
        type: "response.mcp_call_arguments.delta",
        item_id: "mcp_1",
        delta: '{"uniqueKey":"a"}',
      }),
      state,
    );
    mapFoundryEvent(
      ev({
        type: "response.mcp_call_arguments.done",
        item_id: "mcp_1",
        arguments: '{"uniqueKey":"a"}',
      }),
      state,
    );
    mapFoundryEvent(
      ev({
        type: "response.mcp_call_arguments.delta",
        item_id: "mcp_1",
        delta: '{"uniqueKey":"b"}',
      }),
      state,
    );
    const out = mapFoundryEvent(doneItem(""), state);
    expect(out).toMatchObject({ span: { toolInput: { uniqueKey: "b" } } });
  });

  it("forgets an item's arguments once its row is settled", () => {
    const state: FoundryMapState = { sawSearchOutput: false };
    mapFoundryEvent(
      ev({
        type: "response.mcp_call_arguments.done",
        item_id: "mcp_1",
        arguments: '{"uniqueKey":"x"}',
      }),
      state,
    );
    mapFoundryEvent(doneItem("{}"), state);
    expect(state.mcpArguments?.has("mcp_1")).toBe(false);
  });

  it("puts the streamed input on the wire as the tool input", async () => {
    const events = [
      {
        type: "response.output_item.added",
        item: { type: "mcp_call", id: "mcp_1", call_id: "call_1", name: "get_item", arguments: "" },
      },
      { type: "response.mcp_call_arguments.delta", item_id: "mcp_1", delta: '{"uniqueKey":' },
      { type: "response.mcp_call_arguments.delta", item_id: "mcp_1", delta: '"abc-123"}' },
      { type: "response.mcp_call_arguments.done", item_id: "mcp_1", arguments: "{}" },
      {
        type: "response.output_item.done",
        item: {
          type: "mcp_call",
          id: "mcp_1",
          call_id: "call_1",
          name: "get_item",
          arguments: "{}",
          output: '{"subject":"hi"}',
        },
      },
      { type: "response.output_text.delta", delta: "Found it." },
      { type: "response.completed" },
    ].map(ev);
    const client: OpenAIResponsesClientLike = {
      conversations: {
        async create() {
          return { id: "conv_1" };
        },
      },
      responses: {
        async create() {
          return {
            async *[Symbol.asyncIterator]() {
              for (const event of events) yield event;
            },
          };
        },
      },
    } as unknown as OpenAIResponsesClientLike;
    const res = await createFoundryStreamResponse({
      projectEndpoint: "https://proj.example.com",
      agentName: "trial-agent",
      messages: [
        {
          id: "u1",
          role: "user",
          parts: [{ type: "text", text: "open item abc-123" }],
        } as UIMessage,
      ],
      conversationId: null,
      responseHeaders: {},
      activityDetail: "full",
      openAIClientFactory: () => client,
    });
    const wire = await new Response(res.body).text();
    const input = wire.split("\n").find((line) => line.includes('"tool-input-available"'));
    expect(input).toBeDefined();
    expect(input).toContain('"uniqueKey":"abc-123"');
    expect(input).not.toContain('"input":{}');
  });
});
