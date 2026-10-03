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
  expect(src).not.toContain("#d4b483");
  expect(src).not.toContain("#14120f");
  expect(src).not.toContain("FX Hub");
  expect(src).not.toContain("12x");
});

test("the readme describes the web desk header", () => {
  const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
  expect(readme.toLowerCase()).not.toContain("top right");
  expect(readme).toContain("desk:");
  expect(readme).toContain("web rail");
});
