import { expect, test } from "bun:test";
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";
import { App } from "./app";
import { deskChoices } from "./command";

async function frameOf(path: string): Promise<string> {
  const setup = await testRender(<App />, { width: 100, height: 30 });
  await setup.renderOnce();
  act(() => {
    setup.mockInput.typeText("/");
  });
  await setup.renderOnce();
  act(() => {
    setup.mockInput.typeText(path);
  });
  await setup.renderOnce();
  act(() => {
    setup.mockInput.pressEnter();
  });
  await setup.renderOnce();
  const frame = setup.captureCharFrame();
  act(() => setup.renderer.destroy());
  return frame;
}

test("probe families", async () => {
  console.log("DESKS:" + JSON.stringify(deskChoices().map((d) => d.id + "=" + d.label)));
  for (const p of ["portfolio", "pipeline", "strategies", "tools/chat", "settings", "tools/terminal"]) {
    const frame = await frameOf(p);
    console.log("PATHQUERY-START " + p + "\n" + frame + "\nPATHQUERY-END " + p);
  }
  expect(true).toBe(true);
}, 60000);
