import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { moduleCountLabel, moduleCounts, moduleVersion } from "./moduleCounts";
import counts from "./module-counts.json";

/**
 * `module-counts.json` is generated, so the only thing worth testing is that it
 * still matches the sources it claims to have been generated from. Recompute
 * both numbers here and compare: a new endpoint in a spec, or a new
 * `@mcp.tool` in a server, must fail this rather than quietly leave a stale
 * figure on the landing page.
 *
 * The MCP files are read from the repo root, which is two levels up from
 * `apps/digithings-web` — the same place `scripts/fetch_module_counts.py`
 * writes from.
 */

const REPO = resolve(__dirname, "..", "..", "..");

const SPEC_SOURCES: Record<string, string> = {
  digigraph: "digigraph",
  digiquant: "digiquant",
  digisearch: "digisearch",
  digichat: "digichat",
  digikey: "digikey",
  digismith: "digismith",
  digivault: "digivault",
};

const MCP_SOURCES: Record<string, [string, RegExp]> = {
  digigraph: ["digigraph/src/digigraph/mcp_server.py", /^\s*@mcp\.tool/],
  digiquant: ["digiquant/src/digiquant/mcp_server.py", /^\s*@_maybe_tool/],
  digisearch: ["digisearch/src/digisearch/mcp_server.py", /^\s*@mcp\.tool/],
  digivault: ["digivault/src/digivault/tool_dispatch.py", /^\s*@mcp\.tool/],
};

/* module id -> the file that declares its own version. Mirrors
   `VERSION_SOURCES` in scripts/fetch_module_counts.py. */
const VERSION_SOURCES: Record<string, string> = {
  digigraph: "digigraph/pyproject.toml",
  digiquant: "digiquant/pyproject.toml",
  digisearch: "digisearch/pyproject.toml",
  digichat: "apps/digichat/package.json",
  digikey: "digikey/pyproject.toml",
  digismith: "digismith/pyproject.toml",
  digiclaw: "digiclaw/pyproject.toml",
  digibase: "digibase/pyproject.toml",
  digivault: "digivault/pyproject.toml",
  digiskills: "digiskills/pyproject.toml",
};

function read(path: string): string {
  return readFileSync(resolve(REPO, path), "utf8");
}

function declaredVersion(path: string): string {
  const text = read(path);
  if (path.endsWith("package.json")) {
    return (JSON.parse(text) as { version: string }).version;
  }
  const match = text.match(/^\s*version\s*=\s*["']([^"']+)["']/m);
  if (!match) throw new Error(`no version in ${path}`);
  return match[1];
}

describe("module-counts.json", () => {
  it("matches the committed OpenAPI specs", () => {
    for (const [id, service] of Object.entries(SPEC_SOURCES)) {
      const spec = JSON.parse(read(`docs/openapi/${service}.json`)) as { paths?: object };
      const expected = Object.keys(spec.paths ?? {}).length;
      expect(moduleCounts(id).endpoints, `${id} endpoints`).toBe(expected);
    }
  });

  it("matches the MCP server decorator sites", () => {
    for (const [id, [file, pattern]] of Object.entries(MCP_SOURCES)) {
      const expected = read(file)
        .split("\n")
        .filter((line) => pattern.test(line)).length;
      expect(moduleCounts(id).mcpTools, `${id} mcp tools`).toBe(expected);
    }
  });

  it("reports an absence as null, never as zero", () => {
    for (const id of ["digiclaw", "digibase", "digistore", "digilink"]) {
      expect(moduleCounts(id)).toEqual({ endpoints: null, mcpTools: null });
      expect(moduleCountLabel(id)).toBe("");
    }
    /* digichat publishes a spec but runs no MCP server of its own. */
    expect(moduleCounts("digichat").mcpTools).toBeNull();
  });

  it("labels the two numbers a module does publish", () => {
    expect(moduleCountLabel("digiquant")).toBe("22 endpoints · 127 mcp tools");
    expect(moduleCountLabel("digismith")).toBe("3 endpoints");
  });

  it("matches the version each module declares for itself", () => {
    for (const [id, path] of Object.entries(VERSION_SOURCES)) {
      expect(moduleVersion(id), `${id} version`).toBe(declaredVersion(path));
    }
    /* Roadmap modules have no directory, so they declare no version — null,
       not a made-up 0.0.0. */
    for (const id of ["digistore", "digilink"]) {
      expect(moduleVersion(id), `${id} version`).toBeNull();
    }
  });

  it("carries a generated timestamp", () => {
    expect(counts.generatedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });
});
