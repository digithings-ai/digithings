import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "./route";
import { SCHEMA_PROXY_ENV } from "@/lib/mcp/schema-proxy";

const UPSTREAM = "https://mcp.example.com/";
const KEY_HEADER = "x-digi-mcp-key";
const KEY_ENV = "DIGICHAT_MCP_PROXY_KEY";

const ctx = { params: Promise.resolve({ label: "tools" }) };

const rpc = (headers: Record<string, string> = {}) =>
  new Request("https://chat.example.com/api/mcp-proxy/tools", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json", ...headers },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }),
  });

beforeEach(() => {
  delete process.env[SCHEMA_PROXY_ENV];
  delete process.env[KEY_ENV];
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete process.env[SCHEMA_PROXY_ENV];
  delete process.env[KEY_ENV];
});

describe("/api/mcp-proxy/<label> caller authentication", () => {
  it("answers 404 when the proxy is not configured at all", async () => {
    const res = await POST(rpc(), ctx);
    expect(res.status).toBe(404);
  });

  it("answers 503 rather than serving an unauthenticated relay", async () => {
    process.env[SCHEMA_PROXY_ENV] = JSON.stringify({ tools: UPSTREAM });
    const res = await POST(rpc(), ctx);
    expect(res.status).toBe(503);
    expect(((await res.json()) as { error: string }).error).toBe("proxy_key_unconfigured");
  });

  it("answers 401 when the shared secret is missing", async () => {
    process.env[SCHEMA_PROXY_ENV] = JSON.stringify({ tools: UPSTREAM });
    process.env[KEY_ENV] = "s3cret";
    const res = await POST(rpc(), ctx);
    expect(res.status).toBe(401);
  });

  it("answers 401 when the shared secret is wrong", async () => {
    process.env[SCHEMA_PROXY_ENV] = JSON.stringify({ tools: UPSTREAM });
    process.env[KEY_ENV] = "s3cret";
    const res = await POST(rpc({ [KEY_HEADER]: "s3cret-but-longer" }), ctx);
    expect(res.status).toBe(401);
  });

  it("forwards with the right secret and never sends that secret upstream", async () => {
    process.env[SCHEMA_PROXY_ENV] = JSON.stringify({ tools: UPSTREAM });
    process.env[KEY_ENV] = "s3cret";

    const sent: Headers[] = [];
    const upstream = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      sent.push(new Headers(init?.headers));
      return new Response(JSON.stringify({ jsonrpc: "2.0", id: 1, result: { tools: [] } }), {
        headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", upstream);

    const res = await POST(rpc({ [KEY_HEADER]: "s3cret", "x-api-key": "caller-key" }), ctx);
    expect(res.status).toBe(200);
    expect(upstream).toHaveBeenCalledTimes(1);
    expect(sent[0].get("x-api-key")).toBe("caller-key");
    expect(sent[0].get(KEY_HEADER)).toBeNull();
  });
});
