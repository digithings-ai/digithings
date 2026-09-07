import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("POST /api/vanilla-chat", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.resetModules();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  async function post(url: string, body: unknown) {
    const { POST } = await import("./route");
    return POST(
      new Request(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
  }

  it("404s in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const res = await post("http://127.0.0.1:3005/api/vanilla-chat", {
      messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
    });
    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("proxies loopback development traffic to digithings.ai/api/chat", async () => {
    vi.stubEnv("NODE_ENV", "development");
    fetchMock.mockResolvedValue(
      new Response("data: {\"type\":\"text-delta\"}\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
    );
    const res = await post("http://127.0.0.1:3005/api/vanilla-chat", {
      messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
    });
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("text-delta");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://digithings.ai/api/chat");
    const headers = new Headers(init.headers);
    expect(headers.get("x-embed-host")).toBe("digithings.ai");
    expect(headers.get("origin")).toBe("https://digithings.ai");
  });

  it("ignores an unallowlisted DIGICHAT_VANILLA_UPSTREAM (no SSRF)", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("DIGICHAT_VANILLA_UPSTREAM", "https://evil.example/api/chat");
    fetchMock.mockResolvedValue(new Response("ok", { status: 200 }));
    await post("http://127.0.0.1:3005/api/vanilla-chat", {
      messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
    });
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe("https://digithings.ai/api/chat");
  });

  it("returns 502 when the upstream fetch throws", async () => {
    vi.stubEnv("NODE_ENV", "development");
    fetchMock.mockRejectedValue(new Error("connect reset"));
    const res = await post("http://127.0.0.1:3005/api/vanilla-chat", {
      messages: [{ id: "1", role: "user", parts: [{ type: "text", text: "hi" }] }],
    });
    expect(res.status).toBe(502);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("vanilla_upstream_failed");
  });
});
