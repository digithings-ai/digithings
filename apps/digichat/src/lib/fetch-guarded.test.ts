import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import {
  CREDENTIAL_HEADER_NAMES,
  CredentialRedirectError,
  fetchGuarded,
  hasCredentialHeaders,
  sameOrigin,
} from "./fetch-guarded";

/** Placeholder only — never a real secret. */
const FAKE_BYOK = "test-byok-placeholder";
const FAKE_LITELLM = "test-litellm-placeholder";
const FAKE_BEARER = "test-bearer-placeholder";
/** Serialized MCP upstream config that route.ts forwards on X-Digi-Mcp-Servers. */
const MCP_SERVERS_JSON = JSON.stringify([
  {
    id: "linear",
    url: "https://mcp.example.test/sse",
    auth: "bearer",
    token: "test-mcp-token-placeholder",
  },
]);

function listen(server: Server): Promise<number> {
  return new Promise((resolve, reject) => {
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      if (addr && typeof addr === "object") resolve(addr.port);
      else reject(new Error("no port"));
    });
  });
}

function close(server: Server): Promise<void> {
  return new Promise((resolve, reject) => {
    server.close((err) => (err ? reject(err) : resolve()));
  });
}

describe("hasCredentialHeaders / sameOrigin", () => {
  it("detects X-BYOK-Key and X-LiteLLM-Proxy-Key case-insensitively", () => {
    expect(hasCredentialHeaders({ "X-BYOK-Key": FAKE_BYOK })).toBe(true);
    expect(hasCredentialHeaders({ "x-litellm-proxy-key": FAKE_LITELLM })).toBe(true);
    expect(hasCredentialHeaders({ Authorization: `Bearer ${FAKE_BEARER}` })).toBe(true);
    expect(hasCredentialHeaders({ "Content-Type": "application/json" })).toBe(false);
  });

  it("treats different ports as different origins", () => {
    expect(
      sameOrigin(new URL("http://127.0.0.1:1111/a"), new URL("http://127.0.0.1:2222/b")),
    ).toBe(false);
    expect(
      sameOrigin(new URL("http://127.0.0.1:1111/a"), new URL("http://127.0.0.1:1111/b")),
    ).toBe(true);
  });

  it("detects MCP token headers, including future x-digi-mcp-* variants (#3933)", () => {
    expect(CREDENTIAL_HEADER_NAMES).toContain("x-digi-mcp-servers");
    expect(CREDENTIAL_HEADER_NAMES).toContain("x-digi-mcp-session");
    expect(hasCredentialHeaders({ "X-Digi-Mcp-Servers": MCP_SERVERS_JSON })).toBe(true);
    expect(hasCredentialHeaders({ "x-digi-mcp-session": "opaque-overlay" })).toBe(true);
    // Prefix match keeps future MCP credential headers covered without edits.
    expect(hasCredentialHeaders({ "X-Digi-Mcp-Future": "token" })).toBe(true);
  });
});

describe("fetchGuarded redirect posture (#2572)", () => {
  let originA: Server;
  let originB: Server;
  let portA = 0;
  let portB = 0;
  let lastBHeaders: IncomingMessage["headers"] | null = null;
  let bHit = 0;

  beforeAll(async () => {
    originB = createServer((req: IncomingMessage, res: ServerResponse) => {
      bHit += 1;
      lastBHeaders = { ...req.headers };
      res.writeHead(200, { "content-type": "text/plain" });
      res.end("b-ok");
    });
    portB = await listen(originB);

    originA = createServer((_req: IncomingMessage, res: ServerResponse) => {
      res.writeHead(302, { Location: `http://127.0.0.1:${portB}/landed` });
      res.end();
    });
    portA = await listen(originA);
  });

  afterAll(async () => {
    await close(originA);
    await close(originB);
  });

  it("does NOT forward credential headers on a cross-origin 302", async () => {
    bHit = 0;
    lastBHeaders = null;
    const url = `http://127.0.0.1:${portA}/start`;
    await expect(
      fetchGuarded(url, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${FAKE_BEARER}`,
          "X-BYOK-Key": FAKE_BYOK,
          "X-LiteLLM-Proxy-Key": FAKE_LITELLM,
        },
      }),
    ).rejects.toBeInstanceOf(CredentialRedirectError);

    expect(bHit).toBe(0);
    expect(lastBHeaders).toBeNull();
  });

  it("baseline: undici/fetch WOULD forward X-* across origins (documents the defect)", async () => {
    bHit = 0;
    lastBHeaders = null;
    const url = `http://127.0.0.1:${portA}/start`;
    const res = await fetch(url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${FAKE_BEARER}`,
        "X-BYOK-Key": FAKE_BYOK,
        "X-LiteLLM-Proxy-Key": FAKE_LITELLM,
      },
      redirect: "follow",
    });
    expect(res.status).toBe(200);
    expect(bHit).toBe(1);
    // Spec strips Authorization; custom X-* still arrive — the bug we guard against.
    expect(lastBHeaders?.authorization).toBeUndefined();
    expect(lastBHeaders?.["x-byok-key"]).toBe(FAKE_BYOK);
    expect(lastBHeaders?.["x-litellm-proxy-key"]).toBe(FAKE_LITELLM);
  });

  it("does NOT forward MCP token headers on a cross-origin 302 (#3933)", async () => {
    bHit = 0;
    lastBHeaders = null;
    const url = `http://127.0.0.1:${portA}/start`;
    await expect(
      fetchGuarded(url, {
        method: "POST",
        headers: {
          "X-Digi-Mcp-Servers": MCP_SERVERS_JSON,
          "X-Digi-Mcp-Session": "opaque-overlay",
        },
        body: "{}",
      }),
    ).rejects.toBeInstanceOf(CredentialRedirectError);

    expect(bHit).toBe(0);
    expect(lastBHeaders).toBeNull();
  });

  it("baseline: raw fetch WOULD forward X-Digi-Mcp-Servers across origins (#3933)", async () => {
    bHit = 0;
    lastBHeaders = null;
    const url = `http://127.0.0.1:${portA}/start`;
    const res = await fetch(url, {
      method: "GET",
      headers: { "X-Digi-Mcp-Servers": MCP_SERVERS_JSON },
      redirect: "follow",
    });
    expect(res.status).toBe(200);
    expect(bHit).toBe(1);
    // The MCP bearer is in the serialized header — undici forwards it cross-origin.
    expect(lastBHeaders?.["x-digi-mcp-servers"]).toBe(MCP_SERVERS_JSON);
    expect(lastBHeaders?.["x-digi-mcp-servers"]).toContain("test-mcp-token-placeholder");
  });

  it("preserves Request method, body and signal on the credentialed path (#3933)", async () => {
    const req = new Request(`http://127.0.0.1:${portA}/start`, {
      method: "POST",
      headers: { "X-Digi-Mcp-Servers": MCP_SERVERS_JSON },
      body: "payload",
    });
    const spy = vi.fn<typeof fetch>(async () => new Response("ok", { status: 200 }));
    await fetchGuarded(req, undefined, spy as typeof fetch);
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.redirect).toBe("manual");
    expect(init.body).toBeTruthy();
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("cancels the refused redirect response body before throwing (#3933)", async () => {
    let cancelled = false;
    const stream = new ReadableStream({
      cancel() {
        cancelled = true;
      },
    });
    const spy = vi.fn(
      async () =>
        new Response(stream, {
          status: 302,
          headers: { location: "http://cross-origin.example.test/elsewhere" },
        }),
    );
    await expect(
      fetchGuarded(
        "http://127.0.0.1:1/x",
        { headers: { Authorization: `Bearer ${FAKE_BEARER}` } },
        spy as typeof fetch,
      ),
    ).rejects.toBeInstanceOf(CredentialRedirectError);
    expect(cancelled).toBe(true);
  });

  it("follows same-origin redirects while keeping credentials", async () => {
    let hits = 0;
    let sawByok: string | undefined;
    const server = createServer((req: IncomingMessage, res: ServerResponse) => {
      hits += 1;
      if (req.url === "/hop1") {
        res.writeHead(302, { Location: "/hop2" });
        res.end();
        return;
      }
      sawByok = req.headers["x-byok-key"];
      res.writeHead(200, { "content-type": "text/plain" });
      res.end("same-ok");
    });
    const port = await listen(server);
    try {
      const res = await fetchGuarded(`http://127.0.0.1:${port}/hop1`, {
        headers: { "X-BYOK-Key": FAKE_BYOK },
      });
      expect(res.status).toBe(200);
      expect(await res.text()).toBe("same-ok");
      expect(hits).toBe(2);
      expect(sawByok).toBe(FAKE_BYOK);
    } finally {
      await close(server);
    }
  });

  it("passes through non-credentialed fetches without forcing manual redirect", async () => {
    const spy = vi.fn(async () => new Response("ok", { status: 200 }));
    await fetchGuarded("http://127.0.0.1:9/x", { headers: { Accept: "text/plain" } }, spy as typeof fetch);
    expect(spy).toHaveBeenCalledOnce();
    const init = spy.mock.calls[0]?.[1] as RequestInit;
    expect(init.redirect).toBeUndefined();
  });
});
