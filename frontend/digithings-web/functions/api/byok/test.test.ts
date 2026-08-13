import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { onRequestPost } from "./test";

function request(headers: Record<string, string> = {}): { request: Request } {
  return {
    request: new Request("http://localhost/api/byok/test", {
      method: "POST",
      headers,
    }),
  };
}

function jsonFetchResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("POST /api/byok/test", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe("xai provider (added by #2348)", () => {
    it("rejects a key that doesn't start with xai-", async () => {
      const res = await onRequestPost(
        request({ "x-byok-key": "sk-not-xai", "x-byok-provider": "xai" }),
      );
      expect(res.status).toBe(400);
      const body = await res.json();
      expect(body).toEqual({ ok: false, error: "x.ai keys start with xai-." });
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it("calls x.ai's own API — never OpenRouter's — for a valid xai- key", async () => {
      fetchMock.mockResolvedValueOnce(
        jsonFetchResponse({ data: [{ id: "grok-4-3" }] }),
      );

      const res = await onRequestPost(
        request({ "x-byok-key": "xai-realkey", "x-byok-provider": "xai" }),
      );

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("https://api.x.ai/v1/models");
      expect(url).not.toContain("openrouter");
      expect((init.headers as Record<string, string>).Authorization).toBe(
        "Bearer xai-realkey",
      );

      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body).toEqual({ ok: true, model: "grok-4-3" });
    });

    it("surfaces an x.ai-flavored error on a failed live test, not an OpenRouter one", async () => {
      fetchMock.mockResolvedValueOnce(
        jsonFetchResponse({ error: { message: "invalid API key" } }, 401),
      );

      const res = await onRequestPost(
        request({ "x-byok-key": "xai-badkey", "x-byok-provider": "xai" }),
      );

      expect(res.status).toBe(400);
      const body = await res.json();
      expect(body).toEqual({ ok: false, error: "invalid API key" });
    });
  });

  describe("unrecognized provider header (no more silent openrouter coercion)", () => {
    it("returns an explicit 400 instead of coercing to openrouter", async () => {
      const res = await onRequestPost(
        request({ "x-byok-key": "whatever-key", "x-byok-provider": "totally-bogus" }),
      );

      expect(res.status).toBe(400);
      const body = await res.json();
      expect(body).toEqual({ ok: false, error: "Unknown BYOK provider: totally-bogus" });
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it("still defaults to openrouter when no provider header is sent at all", async () => {
      fetchMock.mockResolvedValueOnce(jsonFetchResponse({}));

      const res = await onRequestPost(request({ "x-byok-key": "sk-or-realkey" }));

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("https://openrouter.ai/api/v1/models");
      expect(res.status).toBe(200);
    });
  });

  describe("existing providers are unaffected", () => {
    it("still validates and dispatches anthropic keys as before", async () => {
      fetchMock.mockResolvedValueOnce(
        jsonFetchResponse({ data: [{ id: "claude-3-5-haiku-20241022" }] }),
      );

      const res = await onRequestPost(
        request({ "x-byok-key": "sk-ant-realkey", "x-byok-provider": "anthropic" }),
      );

      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("https://api.anthropic.com/v1/models");
      expect((init.headers as Record<string, string>)["x-api-key"]).toBe("sk-ant-realkey");
      expect(res.status).toBe(200);
    });

    it("still rejects an openai key missing the sk- prefix", async () => {
      const res = await onRequestPost(
        request({ "x-byok-key": "bad-key", "x-byok-provider": "openai" }),
      );
      expect(res.status).toBe(400);
      const body = await res.json();
      expect(body).toEqual({ ok: false, error: "OpenAI keys start with sk-." });
      expect(fetchMock).not.toHaveBeenCalled();
    });
  });
});
