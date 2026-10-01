import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import tools from "../app/_mcp-tools.json";
import { exampleArgs, runDemo, validateArgs, type McpTool } from "./mcp-demo";

const TOOLS = tools as McpTool[];
const byName = (name: string) => {
  const t = TOOLS.find((x) => x.name === name);
  if (!t) throw new Error(`no tool ${name}`);
  return t;
};

describe("mcp tool manifest", () => {
  it("lists every tool the server registers", () => {
    const src = readFileSync(resolve(__dirname, "../../../digiquant/src/digiquant/mcp_server.py"), "utf8");
    const registered = [...src.matchAll(/@_maybe_tool\("([a-z0-9_]+)"\)/g)].map((m) => m[1]).sort();
    expect(TOOLS.map((t) => t.name).sort()).toEqual(registered);
  });

  it("marks the read-scope tools from READ_SCOPE_TOOLS", () => {
    expect(byName("digiquant_list_strategies").scope).toBe("read");
    expect(byName("digiquant_run_backtest").scope).toBe("full");
  });
});

describe("demo execution", () => {
  it("accepts the generated example arguments for every tool", () => {
    for (const t of TOOLS) expect(validateArgs(t, exampleArgs(t)), t.name).toEqual([]);
  });

  it("reports missing, unexpected and mistyped arguments", () => {
    const t = byName("digiquant_run_backtest");
    expect(validateArgs(t, {})).toContain('missing required argument "strategy_name"');
    expect(validateArgs(t, { strategy_name: 3, symbols_json: "[]", nope: 1 })).toEqual(
      expect.arrayContaining(['"strategy_name" must be str', 'unexpected argument "nope"']),
    );
  });

  it("does not register full-scope tools under read scope", () => {
    const t = byName("digiquant_run_backtest");
    const out = runDemo(t, JSON.stringify(exampleArgs(t)), "read");
    expect(out.at(-1)?.kind).toBe("err");
    expect(out.at(-1)?.text).toContain("not registered under --scope read");
  });

  it("returns a demo result, never an executed one", () => {
    const t = byName("digiquant_list_strategies");
    const out = runDemo(t, "{}", "read");
    const last = out.at(-1);
    expect(last?.kind).toBe("out");
    expect(JSON.parse(last?.text ?? "{}")).toMatchObject({ mode: "demo", executed: false });
  });

  it("rejects arguments that are not a JSON object", () => {
    const t = byName("digiquant_list_strategies");
    expect(runDemo(t, "[1]", "full").at(-1)?.text).toContain("JSON object");
    expect(runDemo(t, "{", "full").at(-1)?.text).toContain("not valid JSON");
  });
});
