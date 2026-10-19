import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DELETE, GET, HEAD, POST } from "./[[...path]]/route";

/**
 * /api/mcp/zammad* must FORWARD, not render.
 *
 * The live failure this pins: production does not set DIGICHAT_TRUSTED_PROXIES,
 * so Next owns port 3000 and the Worker's zammad-MCP path reached Next itself —
 * which answered its own 404 page instead of the helpdesk MCP.
 *
 * Nothing here touches the network or 127.0.0.1:8770, so the suite is green
 * with no container running.
 */

const CONTAINER_MCP_URL = "http://127.0.0.1:8770/mcp";

type CapturedCall = { url: string; init: RequestInit };

function captureFetch(reply: () => Response | Promise<Response>) {
  const calls: CapturedCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      calls.push({ url, init: init ?? {} });
      return reply();
    }),
  );
  return calls;
}

function forwardedHeaders(call: CapturedCall): Headers {
  return new Headers(call.init.headers);
}

function bodyText(init: RequestInit): string {
  const body = init.body;
  if (body === undefined || body === null) return "";
  if (typeof body === "string") return body;
  if (body instanceof ArrayBuffer) return new TextDecoder().decode(body);
  if (ArrayBuffer.isView(body)) {
    return new TextDecoder().decode(
      new Uint8Array(body.buffer, body.byteOffset, body.byteLength),
    );
  }
  return "";
}

function mcpCall(): Request {
  // Deliberately carries the headers a real hop sends, including the ones that
  // must NOT be replayed: a caller-supplied content-length is a lie about the
  // bytes we re-send, and Node's fetch refuses transfer-encoding outright.
  return new Request("http://127.0.0.1:3000/api/mcp/zammad/mcp", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-digi-mcp-key": "edge-key-not-forwarded-to-mcp",
      "mcp-session-id": "sess-123",
      host: "digithings.ai",
      connection: "keep-alive",
      "content-length": "999",
      "transfer-encoding": "chunked",
    },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }),
  });
}

beforeEach(() => {
  vi.stubEnv("ZAMMAD_MCP_URL", undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("/api/mcp/zammad passthrough", () => {
  it("forwards POST /api/mcp/zammad/mcp to the in-container MCP endpoint with the same method and body", async () => {
    const calls = captureFetch(
      () =>
        new Response(JSON.stringify({ jsonrpc: "2.0", id: 1, result: { tools: [] } }), {
          status: 200,
          headers: { "content-type": "application/json", "mcp-session-id": "sess-123" },
        }),
    );

    const res = await POST(mcpCall());

    expect(res.status).toBe(200);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(CONTAINER_MCP_URL);
    expect(calls[0].init.method).toBe("POST");
    expect(bodyText(calls[0].init)).toBe('{"jsonrpc":"2.0","id":1,"method":"tools/list"}');

    const sent = forwardedHeaders(calls[0]);
    // The edge gate's own header and the MCP session header survive the hop.
    expect(sent.get("content-type")).toBe("application/json");
    expect(sent.get("x-digi-mcp-key")).toBe("edge-key-not-forwarded-to-mcp");
    expect(sent.get("mcp-session-id")).toBe("sess-123");
    // ...and nothing that describes the previous hop is replayed.
    for (const name of ["host", "connection", "content-length", "transfer-encoding"]) {
      expect(sent.get(name)).toBeNull();
    }

    // The upstream answer is streamed back, not replaced by a page.
    expect(res.headers.get("content-type")).toBe("application/json");
    expect(res.headers.get("mcp-session-id")).toBe("sess-123");
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(await res.json()).toEqual({ jsonrpc: "2.0", id: 1, result: { tools: [] } });
  });

  it("forwards GET and DELETE with no body, and honours ZAMMAD_MCP_URL", async () => {
    vi.stubEnv("ZAMMAD_MCP_URL", "http://zammad-mcp:8770/mcp");
    const calls = captureFetch(() => new Response("", { status: 202 }));

    const get = await GET(new Request("http://127.0.0.1:3000/api/mcp/zammad/mcp"));
    const del = await DELETE(new Request("http://127.0.0.1:3000/api/mcp/zammad/mcp", { method: "DELETE" }));

    expect(get.status).toBe(202);
    expect(del.status).toBe(202);
    expect(calls.map((c) => c.url)).toEqual([
      "http://zammad-mcp:8770/mcp",
      "http://zammad-mcp:8770/mcp",
    ]);
    expect(calls.map((c) => c.init.method)).toEqual(["GET", "DELETE"]);
    // GET/HEAD carry no body at all (fetch rejects a body on GET/HEAD);
    // DELETE's verbatim bytes are simply zero-length here.
    expect(calls[0].init.body ?? null).toBeNull();
    expect(bodyText(calls[1].init)).toBe("");
    expect(get.headers.get("cache-control")).toBe("no-store");
  });

  it("returns 502 zammad_mcp_unreachable when the MCP server is down — never a 200", async () => {
    captureFetch(() => {
      throw new TypeError("fetch failed");
    });

    const res = await POST(mcpCall());

    expect(res.status).toBe(502);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(await res.json()).toEqual({ error: "zammad_mcp_unreachable" });
  });

  it("passes an upstream refusal through as-is instead of masking it", async () => {
    captureFetch(
      () =>
        new Response("unauthorized", {
          status: 401,
          headers: {
            "content-type": "text/plain",
            // What Node's fetch leaves behind after transparently decoding a
            // gzip body: both headers would corrupt a passthrough.
            "content-encoding": "gzip",
            "content-length": "45",
          },
        }),
    );

    const res = await POST(mcpCall());

    expect(res.status).toBe(401);
    expect(await res.text()).toBe("unauthorized");
    expect(res.headers.get("content-encoding")).toBeNull();
    expect(res.headers.get("content-length")).toBeNull();
  });

  it("handles a HEAD probe without a body", async () => {
    const calls = captureFetch(() => new Response(null, { status: 200 }));

    const res = await HEAD(new Request("http://127.0.0.1:3000/api/mcp/zammad/mcp", { method: "HEAD" }));

    expect(res.status).toBe(200);
    expect(calls[0].init.method).toBe("HEAD");
    expect(calls[0].init.body ?? null).toBeNull();
  });
});
