import { test } from "bun:test";
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";
import { FxDesk } from "./fx";

const BODY = {
  sessions: [
    { session: "Asia", state: null, note: null },
    { session: "London", state: null, note: null },
    { session: "New York", state: null, note: null },
  ],
};

function stub() {
  (globalThis as unknown as { fetch: unknown }).fetch = async () =>
    new Response(JSON.stringify({ status: "ok", source: "static-sessions", data: BODY }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
}

test("desk frames", async () => {
  stub();
  for (const h of [24, 28, 30, 36, 40]) {
    const setup = await testRender(
      <box width="100%" height="100%" flexDirection="column" backgroundColor="#0B0C0E">
        <box flexShrink={0} flexDirection="column">
          <box height={2} />
          <box height={1} />
        </box>
        <box flexGrow={1} flexDirection="row">
          <box width={16} />
          <box flexGrow={1}>
            <FxDesk path="/fx" api="http://127.0.0.1:9" />
          </box>
        </box>
        <box height={2} />
      </box>,
      { width: 120, height: h },
    );
    await act(async () => {
      for (let i = 0; i < 8; i += 1) {
        setup.renderOnce();
        await new Promise((r) => setTimeout(r, 5));
      }
    });
    const c = setup.captureCharFrame();
    act(() => setup.renderer.destroy());
    console.log(`\n########## terminal height ${h} ##########`);
    console.log(c);
  }
});
