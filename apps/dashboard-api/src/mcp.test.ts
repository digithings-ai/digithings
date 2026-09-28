/**
 * Slice 0006 MCP tests: secret gate (fail-closed 401, stack `/_stack/mcp`
 * idiom) + JSON-RPC tools/list + tools/call over the shared route dispatch.
 */
import { describe, expect, it } from "vitest";
import app, { type Env } from "./index";
import { MCP_TOOLS } from "./mcp";

const KEY = "test-mcp-key";
const ENV: Env = { MCP_EDGE_KEY: KEY };
const NO_ENV: Env = {};

function post(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("https://x/mcp", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

const auth = { "x-digi-mcp-key": KEY };

describe("POST /mcp gate", () => {
  it("401s without a key", async () => {
    const res = await app.fetch(
      post({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} }),
      ENV,
    );
    expect(res.status).toBe(401);
  });

  it("401s on a wrong key", async () => {
    const res = await app.fetch(
      post({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} }, { "x-digi-mcp-key": "nope" }),
      ENV,
    );
    expect(res.status).toBe(401);
  });

  it("401s when no secret is configured (fail closed)", async () => {
    const res = await app.fetch(
      post({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} }, auth),
      NO_ENV,
    );
    expect(res.status).toBe(401);
  });

  it("rejects non-POST with bad_request", async () => {
    const res = await app.fetch(new Request("https://x/mcp", { headers: auth }), ENV);
    expect(res.status).toBe(400);
  });
});

describe("POST /mcp tools", () => {
  it("tools/list names one tool per read-only route group", async () => {
    const res = await app.fetch(
      post({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} }, auth),
      ENV,
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as { result: { tools: Array<{ name: string }> } };
    const names = body.result.tools.map((t) => t.name);
    expect(names).toEqual(MCP_TOOLS.map((t) => t.name));
    for (const want of ["get_portfolio", "get_brief", "get_ledger"]) {
      expect(names).toContain(want);
    }
  });

  it("tools/call runs the shared builder (same envelope as HTTP)", async () => {
    const res = await app.fetch(
      post(
        { jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "get_brief", arguments: {} } },
        auth,
      ),
      ENV,
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      result: { content: Array<{ text: string }>; isError: boolean };
    };
    expect(body.result.isError).toBe(false);
    const text = JSON.parse(body.result.content[0].text) as {
      data: { book_as_of: string };
      provenance: Record<string, unknown>;
    };
    expect(text.data.book_as_of).toBe("2026-08-28");
    expect(text.provenance).toHaveProperty("source");
  });

  it("tools/call forwards arguments as route query params", async () => {
    const res = await app.fetch(
      post(
        {
          jsonrpc: "2.0",
          id: 3,
          method: "tools/call",
          params: { name: "get_ledger", arguments: { ticker: "NOPE" } },
        },
        auth,
      ),
      ENV,
    );
    const body = (await res.json()) as { result: { content: Array<{ text: string }> } };
    const text = JSON.parse(body.result.content[0].text) as { data: { events: unknown[] } };
    expect(text.data.events).toEqual([]);
  });

  it("unknown tool is -32602, unknown method is -32601", async () => {
    const badTool = await app.fetch(
      post({ jsonrpc: "2.0", id: 4, method: "tools/call", params: { name: "drop_tables" } }, auth),
      ENV,
    );
    const badToolBody = (await badTool.json()) as { error: { code: number } };
    expect(badToolBody.error.code).toBe(-32602);
    const badMethod = await app.fetch(
      post({ jsonrpc: "2.0", id: 5, method: "tools/destroy", params: {} }, auth),
      ENV,
    );
    const badMethodBody = (await badMethod.json()) as { error: { code: number } };
    expect(badMethodBody.error.code).toBe(-32601);
  });
});
