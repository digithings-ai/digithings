import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { moduleById } from "@digithings/ui";
import { stackModuleHref } from "./stack-showcase";

describe("stack showcase cells", () => {
  it("prefers an in-site registry link, then the first registry href", () => {
    expect(stackModuleHref("digichat")).toBe("/chat");
    const graph = moduleById("digigraph");
    expect(stackModuleHref("digigraph")).toBe(graph?.links[0]?.href);
    expect(stackModuleHref("digigraph")).toMatch(/^https?:/);
  });

  it("renders each cell as a link in tab order", () => {
    const path = fileURLToPath(new URL("./stack-showcase.tsx", import.meta.url));
    const src = readFileSync(path, "utf8");
    const start = src.indexOf("function Cell(");
    const end = src.indexOf("function Detail(", start);
    const cell = src.slice(start, end);
    expect(cell).toContain("<a");
    expect(cell).toContain("href={href}");
    expect(cell).not.toContain("tabIndex={-1}");
    expect(cell).not.toContain("<div\n      data-module");
  });
});
