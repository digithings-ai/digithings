import { beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/mcp-proxy/[label]/route";
import {
  proxySchemaNormalizedMcp,
  resetSchemaProxyCacheForTests,
  schemaProxyTarget,
  schemaProxyUpstream,
  SCHEMA_PROXY_ENV,
  toolErrorAsResult,
} from "./schema-proxy";

const UPSTREAM = "https://mcp.example.com/";
const URL_PATH = "https://chat.example.com/api/mcp-proxy/tools";
const env = { [SCHEMA_PROXY_ENV]: JSON.stringify({ tools: UPSTREAM }) };

const SDK_TOOL = {
  name: "list_reports",
  description: "List reports.",
  inputSchema: {
    type: "object",
    properties: {
      pageSize: { type: ["string", "integer", "null"], default: 0 },
      marker: { type: "string", default: null },
    },
  },
};
const NORMALIZED_PROPS = { pageSize: { type: ["integer", "null"] }, marker: { type: "string" } };

type Call = { url: string; init: RequestInit };

function fakeFetch(reply: (body: Record<string, unknown>) => Response) {
  const calls: Call[] = [];
  const impl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init: init ?? {} });
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    return reply(body);
  }) as unknown as typeof fetch;
  return { calls, impl };
}

function rpc(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("https://chat.example.com/api/mcp-proxy/tools", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json, text/event-stream", ...headers },
    body: JSON.stringify(body),
  });
}

const listReply = (id: unknown) =>
  new Response(JSON.stringify({ jsonrpc: "2.0", id, result: { tools: [SDK_TOOL] } }), {
    headers: { "content-type": "application/json" },
  });

beforeEach(() => resetSchemaProxyCacheForTests());

describe("schemaProxyUpstream", () => {
  it("resolves only a configured label to an https (or loopback http) URL", () => {
    expect(schemaProxyUpstream("tools", env)).toBe(UPSTREAM);
    expect(schemaProxyUpstream("other", env)).toBeNull();
    expect(schemaProxyUpstream("tools", {})).toBeNull();
    expect(schemaProxyUpstream("../x", env)).toBeNull();
    expect(schemaProxyUpstream("tools", { [SCHEMA_PROXY_ENV]: "not json" })).toBeNull();
    expect(schemaProxyUpstream("tools", { [SCHEMA_PROXY_ENV]: '{"tools":"http://mcp.example.com/"}' })).toBeNull();
    expect(schemaProxyUpstream("tools", { [SCHEMA_PROXY_ENV]: '{"tools":"https://u:p@mcp.example.com/"}' })).toBeNull();
    expect(schemaProxyUpstream("tools", { [SCHEMA_PROXY_ENV]: '{"tools":"http://127.0.0.1:8770/mcp"}' })).toBe(
      "http://127.0.0.1:8770/mcp",
    );
  });

  it("answers 404 through the route when the proxy is not configured", async () => {
    delete process.env[SCHEMA_PROXY_ENV];
    const res = await POST(rpc({ jsonrpc: "2.0", id: 1, method: "tools/list" }), {
      params: Promise.resolve({ label: "tools" }),
    });
    expect(res.status).toBe(404);
  });
});

describe("proxySchemaNormalizedMcp", () => {
  it("normalizes a JSON tools/list reply and forwards the caller's auth, not its cookies", async () => {
    const { calls, impl } = fakeFetch((b) => listReply(b.id));
    const res = await proxySchemaNormalizedMcp(
      rpc({ jsonrpc: "2.0", id: 7, method: "tools/list" }, { "x-api-key": "k", cookie: "c=1" }),
      "tools",
      { fetchImpl: impl, env },
    );
    const body = (await res.json()) as { result: { tools: Array<{ inputSchema: { properties: unknown } }> } };
    expect(body.result.tools[0].inputSchema.properties).toEqual(NORMALIZED_PROPS);
    expect(calls[0].url).toBe(UPSTREAM);
    const sent = new Headers(calls[0].init.headers);
    expect(sent.get("x-api-key")).toBe("k");
    expect(sent.get("cookie")).toBeNull();
  });

  it("normalizes a tools/list reply streamed as SSE, split across chunks", async () => {
    const payload = `event: message\ndata: ${JSON.stringify({ jsonrpc: "2.0", id: "a", result: { tools: [SDK_TOOL] } })}\n\n`;
    const { impl } = fakeFetch(() => {
      const enc = new TextEncoder();
      const mid = Math.floor(payload.length / 2);
      const stream = new ReadableStream<Uint8Array>({
        start(c) {
          c.enqueue(enc.encode(payload.slice(0, mid)));
          c.enqueue(enc.encode(payload.slice(mid)));
          c.close();
        },
      });
      return new Response(stream, { headers: { "content-type": "text/event-stream" } });
    });
    const res = await proxySchemaNormalizedMcp(rpc({ jsonrpc: "2.0", id: "a", method: "tools/list" }), "tools", {
      fetchImpl: impl,
      env,
    });
    const text = await res.text();
    expect(text.startsWith("event: message\n")).toBe(true);
    const data = JSON.parse(text.split("\n").find((l) => l.startsWith("data: "))!.slice(6)) as {
      result: { tools: Array<{ inputSchema: { properties: unknown } }> };
    };
    expect(data.result.tools[0].inputSchema.properties).toEqual(NORMALIZED_PROPS);
  });

  it("coerces tools/call arguments onto the original schema after a tools/list", async () => {
    const { calls, impl } = fakeFetch((b) =>
      b.method === "tools/list"
        ? listReply(b.id)
        : new Response(JSON.stringify({ jsonrpc: "2.0", id: b.id, result: { content: [] } }), {
            headers: { "content-type": "application/json" },
          }),
    );
    await proxySchemaNormalizedMcp(rpc({ jsonrpc: "2.0", id: 1, method: "tools/list" }), "tools", { fetchImpl: impl, env });
    await proxySchemaNormalizedMcp(
      rpc({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "list_reports", arguments: { pageSize: 20, marker: null } } }),
      "tools",
      { fetchImpl: impl, env },
    );
    expect(calls).toHaveLength(2);
    expect(JSON.parse(String(calls[1].init.body)).params.arguments).toEqual({ pageSize: "20" });
  });

  it("probes tools/list once on a cold cache, with the caller's headers, before coercing", async () => {
    const { calls, impl } = fakeFetch((b) =>
      b.method === "tools/list"
        ? listReply(b.id)
        : new Response(JSON.stringify({ jsonrpc: "2.0", id: b.id, result: {} }), { headers: { "content-type": "application/json" } }),
    );
    await proxySchemaNormalizedMcp(
      rpc({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "list_reports", arguments: { pageSize: 5 } } }, { "x-api-key": "k" }),
      "tools",
      { fetchImpl: impl, env },
    );
    expect(calls).toHaveLength(2);
    expect(JSON.parse(String(calls[0].init.body)).method).toBe("tools/list");
    expect(new Headers(calls[0].init.headers).get("x-api-key")).toBe("k");
    expect(JSON.parse(String(calls[1].init.body)).params.arguments).toEqual({ pageSize: "5" });
  });

  it("forwards uncoerced when the probe fails, and passes other replies through untouched", async () => {
    const { calls, impl } = fakeFetch((b) =>
      b.method === "tools/list"
        ? new Response("nope", { status: 500 })
        : new Response('{"jsonrpc":"2.0","id":4,"result":{"x":1}}', { headers: { "content-type": "application/json" } }),
    );
    const res = await proxySchemaNormalizedMcp(
      rpc({ jsonrpc: "2.0", id: 4, method: "tools/call", params: { name: "list_reports", arguments: { pageSize: 5 } } }),
      "tools",
      { fetchImpl: impl, env },
    );
    expect(JSON.parse(String(calls[1].init.body)).params.arguments).toEqual({ pageSize: 5 });
    expect(await res.text()).toBe('{"jsonrpc":"2.0","id":4,"result":{"x":1}}');
  });

  it("answers 502 when the upstream is unreachable and 413 on an oversized body", async () => {
    const down = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof fetch;
    const res = await proxySchemaNormalizedMcp(rpc({ jsonrpc: "2.0", id: 1, method: "ping" }), "tools", { fetchImpl: down, env });
    expect(res.status).toBe(502);
    const big = new Request("https://chat.example.com/api/mcp-proxy/tools", { method: "POST", body: "x".repeat(1_000_001) });
    expect((await proxySchemaNormalizedMcp(big, "tools", { fetchImpl: down, env })).status).toBe(413);
  });

  it("refuses a declared oversized body without reading it or dialling the upstream", async () => {
    const { calls, impl } = fakeFetch((b) => listReply(b.id));
    const declared = new Request(URL_PATH, {
      method: "POST",
      headers: { "content-length": "1000001" },
      body: "{}",
    });
    const res = await proxySchemaNormalizedMcp(declared, "tools", { fetchImpl: impl, env });
    expect(res.status).toBe(413);
    expect(calls).toHaveLength(0);
  });

  it("stops a chunked body at the cap while it streams, before the upstream is dialled", async () => {
    const { calls, impl } = fakeFetch((b) => listReply(b.id));
    let pulled = 0;
    const chunk = new Uint8Array(100_000).fill(120);
    const body = new ReadableStream({
      pull(controller) {
        pulled += 1;
        controller.enqueue(chunk);
        if (pulled >= 50) controller.close();
      },
    });
    const chunked = new Request(URL_PATH, { method: "POST", body, duplex: "half" } as RequestInit);
    expect(chunked.headers.get("content-length")).toBeNull();
    const res = await proxySchemaNormalizedMcp(chunked, "tools", { fetchImpl: impl, env });
    expect(res.status).toBe(413);
    expect(calls).toHaveLength(0);
    expect(pulled).toBeLessThan(50);
  });

  it("propagates the caller's abort to the forwarded request", async () => {
    const ac = new AbortController();
    let seen: AbortSignal | null | undefined;
    const impl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      seen = init?.signal;
      return new Response("{}", { headers: { "content-type": "application/json" } });
    }) as unknown as typeof fetch;
    const req = new Request(URL_PATH, { method: "POST", body: "{}", signal: ac.signal });
    await proxySchemaNormalizedMcp(req, "tools", { fetchImpl: impl, env });
    expect(seen?.aborted).toBe(false);
    ac.abort();
    expect(seen?.aborted).toBe(true);
  });

  it("answers 504 when the upstream returns no headers in time", async () => {
    const hung = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new Error("aborted")));
        }),
    ) as unknown as typeof fetch;
    const res = await proxySchemaNormalizedMcp(rpc({ jsonrpc: "2.0", id: 1, method: "ping" }), "tools", {
      fetchImpl: hung,
      env,
      headersTimeoutMs: 10,
    });
    expect(res.status).toBe(504);
    expect(await res.json()).toEqual({ error: "mcp_upstream_timeout" });
  });
});

describe("toolErrorsAsResults", () => {
  const softEnv = { [SCHEMA_PROXY_ENV]: JSON.stringify({ tools: { url: UPSTREAM, toolErrorsAsResults: true } }) };
  const errorReply = (id: unknown) =>
    new Response(
      `event: message\ndata: ${JSON.stringify({ jsonrpc: "2.0", id, result: { isError: true, content: [{ type: "text", text: "Apollo request failed (500): boom" }] } })}\n\n`,
      { headers: { "content-type": "text/event-stream" } },
    );

  it("is off unless the label opts in", () => {
    expect(schemaProxyTarget("tools", env)?.toolErrorsAsResults).toBe(false);
    expect(schemaProxyTarget("tools", softEnv)).toEqual({ url: UPSTREAM, toolErrorsAsResults: true });
  });

  it("restates an isError result as a normal result naming the error", () => {
    const out = toolErrorAsResult({ isError: true, content: [{ type: "text", text: "bad pageSize" }] }) as {
      isError: boolean;
      content: Array<{ text: string }>;
    };
    expect(out.isError).toBe(false);
    expect(out.content[0].text).toContain("TOOL ERROR: bad pageSize");
    expect(out.content[0].text).toContain("Do not invent a result");
    const ok = { content: [{ type: "text", text: "rows" }] };
    expect(toolErrorAsResult(ok)).toBe(ok);
  });

  it("softens a streamed tools/call error only when opted in", async () => {
    const call = { jsonrpc: "2.0", id: 9, method: "tools/call", params: { name: "list_reports", arguments: {} } };
    const { impl } = fakeFetch((b) => (b.method === "tools/list" ? listReply(b.id) : errorReply(b.id)));
    const soft = await (await proxySchemaNormalizedMcp(rpc(call), "tools", { fetchImpl: impl, env: softEnv })).text();
    expect(soft).toContain('"isError":false');
    expect(soft).toContain("TOOL ERROR: Apollo request failed (500): boom");
    const hard = await (await proxySchemaNormalizedMcp(rpc(call), "tools", { fetchImpl: impl, env })).text();
    expect(hard).toContain('"isError":true');
  });
});
