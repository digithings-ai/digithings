import { test } from "bun:test";
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";
import { FxDesk } from "./fx";

/** QA probe: paint the whole FX desk at real terminal sizes to learn the
 * painted height of the fx-sessions pane (4 of 12 grid rows) in situ. */

test("desk frame", async () => {
  for (const h of [24, 30, 40]) {
    const setup = await testRender(
      <box width="100%" height="100%" flexDirection="column" backgroundColor="#0B0C0E">
        <box flexShrink={0} height={2} />
        <box flexGrow={1} flexDirection="row">
          <box width={16} />
          <box flexGrow={1}>
            <FxDesk path="/fx" api="http://127.0.0.1:9" />
          </box>
        </box>
        <box height={1} />
      </box>,
      { width: 120, height: h },
    );
    for (let i = 0; i < 3; i += 1) await setup.renderOnce();
    const c = setup.captureCharFrame();
    act(() => setup.renderer.destroy());
    console.log(`\n########## terminal height ${h} ##########`);
    console.log(c);
  }
});
