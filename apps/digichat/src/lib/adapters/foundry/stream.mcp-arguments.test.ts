import { describe, expect, it } from "vitest";

import { mapFoundryEvent, type FoundryMapState, type FoundryStreamEvent } from "./stream";

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
});
