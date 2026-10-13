import { expect, test } from "bun:test";
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";
import { App } from "./app";

test("probe fg encodings", async () => {
  const setup = await testRender(<App />, { width: 100, height: 30 });
  await setup.renderOnce();
  const spans = setup.captureSpans() as unknown as {
    lines: Array<{ spans: Array<{ text: string; fg: unknown }> }>;
  };
  const fgs = new Map<string, string[]>();
  for (const line of spans.lines) {
    for (const span of line.spans) {
      const key = JSON.stringify(span.fg);
      if (!fgs.has(key)) fgs.set(key, []);
      const texts = fgs.get(key);
      if (texts && texts.length < 2) texts.push(span.text.slice(0, 20));
    }
  }
  for (const [fg, texts] of fgs) {
    console.log("FG:" + fg.slice(0, 120) + " texts=" + JSON.stringify(texts));
  }
  act(() => setup.renderer.destroy());
  expect(true).toBe(true);
}, 30000);
