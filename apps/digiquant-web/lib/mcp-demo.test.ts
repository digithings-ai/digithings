import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import tools from "../app/_mcp-tools.json";
import { cycleName, exampleArgs, runDemo, validateArgs, type McpTool } from "./mcp-demo";

const TOOLS = tools as McpTool[];
const byName = (name: string) => {
  const t = TOOLS.find((x) => x.name === name);
  if (!t) throw new Error(`no tool ${name}`);
  return t;
};

describe("mcp tool manifest", () => {
  // The band lists the audited subset (gen_mcp_manifest.py), never a name the server does not register.
  it("lists only tools the server registers", () => {
    const src = readFileSync(resolve(__dirname, "../../../digiquant/src/digiquant/mcp_server.py"), "utf8");
    // Decorators keep the internal digifetch_ key. The server registers that
    // family under gloomberb_ only (DIG-3313).
    const registered = new Set(
      [...src.matchAll(/@_maybe_tool\("([a-z0-9_]+)"\)/g)].map((m) =>
        m[1].startsWith("digifetch_") ? `gloomberb_${m[1].slice("digifetch_".length)}` : m[1],
      ),
    );
    expect(TOOLS.length).toBeGreaterThan(0);
    for (const t of TOOLS) expect(registered.has(t.name), t.name).toBe(true);
  });

  it("marks every tool with a scope", () => {
    for (const t of TOOLS) expect(["read", "full"], t.name).toContain(t.scope);
    expect(byName("digiquant_run_optimize").scope).toBe("full");
  });
});

describe("demo execution", () => {
  it("accepts the generated example arguments for every tool", () => {
    for (const t of TOOLS) expect(validateArgs(t, exampleArgs(t)), t.name).toEqual([]);
  });

  it("reports missing, unexpected and mistyped arguments", () => {
    const t = byName("digiquant_run_optimize");
    expect(validateArgs(t, {})).toContain('missing required argument "strategy_name"');
    expect(validateArgs(t, { strategy_name: 3, symbols_json: "[]", nope: 1 })).toEqual(
      expect.arrayContaining(['"strategy_name" must be str', 'unexpected argument "nope"']),
    );
  });

  it("does not register full-scope tools under read scope", () => {
    const t = byName("digiquant_run_optimize");
    const out = runDemo(t, JSON.stringify(exampleArgs(t)), "read");
    expect(out.at(-1)?.kind).toBe("err");
    expect(out.at(-1)?.text).toContain("not registered under --scope read");
  });

  it("returns a demo result, never an executed one", () => {
    const t = byName("luxalgo_edge_symbols");
    const out = runDemo(t, "{}", "full");
    const last = out.at(-1);
    expect(last?.kind).toBe("out");
    expect(JSON.parse(last?.text ?? "{}")).toMatchObject({ mode: "demo", executed: false });
  });

  it("rejects arguments that are not a JSON object", () => {
    const t = byName("luxalgo_edge_symbols");
    expect(runDemo(t, "[1]", "full").at(-1)?.text).toContain("JSON object");
    expect(runDemo(t, "{", "full").at(-1)?.text).toContain("not valid JSON");
  });
});

describe("cycleName", () => {
  const names = ["a", "b", "c"];

  it("wraps arrow movement through the visible tools", () => {
    expect(cycleName(names, "a", 1)).toBe("b");
    expect(cycleName(names, "c", 1)).toBe("a");
    expect(cycleName(names, "a", -1)).toBe("c");
  });

  it("lands on an end when the current name is filtered out", () => {
    expect(cycleName(names, "missing", 1)).toBe("a");
    expect(cycleName(names, "missing", -1)).toBe("c");
    expect(cycleName([], "a", 1)).toBe("a");
  });
});
