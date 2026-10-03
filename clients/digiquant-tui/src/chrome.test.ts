import { readFileSync } from "node:fs";
import { expect, test } from "bun:test";

test("the header is mark, then desk, then the path field", () => {
  const src = readFileSync(new URL("./app.tsx", import.meta.url), "utf8");
  const mark = src.indexOf("<PixelMark />");
  const desk = src.indexOf("desk:");
  const pathField = src.indexOf('placeholder="/ go to…"');
  expect(mark).toBeGreaterThan(-1);
  expect(desk).toBeGreaterThan(mark);
  expect(pathField).toBeGreaterThan(desk);
  expect(src).toContain('name === "d"');
  expect(src).toContain("searchCommandPages");
  expect(src).toContain("isPublicPage");
  expect(src).toContain("stepRailCols");
  expect(src).toContain("[ ] sidebar");
  expect(src).not.toContain("#d4b483");
  expect(src).not.toContain("#14120f");
  expect(src).not.toContain("FX Hub");
  expect(src).not.toContain("12x");
  const headerEnd = src.indexOf('border={["bottom"]}');
  const overlay = src.indexOf('position="absolute" top={0} left={0} width="100%" zIndex={8}');
  const hits = src.indexOf("<PathHits");
  expect(headerEnd).toBeGreaterThan(mark);
  expect(overlay).toBeGreaterThan(headerEnd);
  expect(hits).toBeGreaterThan(overlay);
});

test("the readme describes the web desk header", () => {
  const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
  expect(readme.toLowerCase()).not.toContain("top right");
  expect(readme).toContain("desk:");
  expect(readme).toContain("web rail");
});
