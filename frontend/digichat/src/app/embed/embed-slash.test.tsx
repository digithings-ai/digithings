// @vitest-environment happy-dom
/**
 * Public /embed slash surface (#3418 / #3556).
 *
 * digichat 2.0 mounts CliThread — palette/behavior assertions live in
 * cli-thread.test.tsx. This file pins the embed host wiring in source.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const embedClientSrc = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "embed-client.tsx"),
  "utf8",
);

describe("public /embed slash surface (#3418)", () => {
  it("renders CliThread (not DigiChatSession)", () => {
    expect(embedClientSrc).toMatch(/CliThread/);
    expect(embedClientSrc).not.toMatch(/DigiChatSession/);
  });

  it("drops the top-right LanguageSelect once /lang is wired", () => {
    expect(embedClientSrc).not.toMatch(/LanguageSelect/);
    expect(embedClientSrc).toMatch(/onLanguageChange=\{setLanguage\}/);
    expect(embedClientSrc).toMatch(/forceTool/);
    expect(embedClientSrc).toMatch(/onReset=\{chat\.reset\}/);
  });

  it("wires turn mutation and websearch slash intercept", () => {
    expect(embedClientSrc).toMatch(/allowTurnMutation/);
    expect(embedClientSrc).toMatch(/onRegenerate=\{chat\.regenerate\}/);
    expect(embedClientSrc).toMatch(/onEditLastUser=\{chat\.editLastUser\}/);
    expect(embedClientSrc).toMatch(/parsed\.command\.id === "websearch"/);
  });
});
