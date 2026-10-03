import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FALLBACK_MODELS, onRequestPost } from "./test";

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
  it("copies config/byok-providers.json fallbackModels", () => {
    const path = fileURLToPath(
      new URL("../../../../../config/byok-providers.json", import.meta.url),
    );
    const catalog = JSON.parse(readFileSync(path, "utf8")) as {
      id: string;
      fallbackModels: string[];
    }[];
    for (const entry of catalog) {
      expect(FALLBACK_MODELS[entry.id as keyof typeof FALLBACK_MODELS]).toEqual(
        entry.fallbackModels,
      );
    }
  });

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

  describe("secret-derived responses are never cached (#2348 minor finding 7)", () => {
    it("sets Cache-Control: no-store on a validation-error response", async () => {
      const res = await onRequestPost(
        request({ "x-byok-key": "sk-not-xai", "x-byok-provider": "xai" }),
      );
      expect(res.status).toBe(400);
      expect(res.headers.get("cache-control")).toBe("no-store");
    });

    it("sets Cache-Control: no-store on a successful live-test response", async () => {
      fetchMock.mockResolvedValueOnce(jsonFetchResponse({ data: [{ id: "grok-4-3" }] }));
      const res = await onRequestPost(
        request({ "x-byok-key": "xai-realkey", "x-byok-provider": "xai" }),
      );
      expect(res.status).toBe(200);
      expect(res.headers.get("cache-control")).toBe("no-store");
    });
  });

  describe("upstream error passthrough is sanitized defensively (#2348 minor finding 7)", () => {
    it("redacts the submitted key if a provider ever echoes it back in an error message", async () => {
      fetchMock.mockResolvedValueOnce(
        jsonFetchResponse({ error: { message: "invalid key: xai-realkey supplied" } }, 401),
      );
      const res = await onRequestPost(
        request({ "x-byok-key": "xai-realkey", "x-byok-provider": "xai" }),
      );
      const body = await res.json();
      expect(body.error).not.toContain("xai-realkey");
      expect(body.error).toBe("invalid key: [redacted] supplied");
    });

    it("caps an unexpectedly long upstream error message", async () => {
      const longMessage = "x".repeat(1000);
      fetchMock.mockResolvedValueOnce(jsonFetchResponse({ error: { message: longMessage } }, 401));
      const res = await onRequestPost(
        request({ "x-byok-key": "xai-realkey", "x-byok-provider": "xai" }),
      );
      const body = await res.json();
      expect(body.error.length).toBeLessThan(longMessage.length);
      expect(body.error.endsWith("…")).toBe(true);
    });
  });

  describe("unrecognized provider header (no more silent openrouter coercion)", () => {
    it("returns an explicit 400 instead of coercing to openrouter", async () => {
      const res = await onRequestPost(
        request({ "x-byok-key": "whatever-key", "x-byok-provider": "totally-bogus" }),
      );

      expect(res.status).toBe(400);
      const body = await res.json();
      expect(body).toEqual({ ok: false, error: "Unknown BYOK provider." });
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

  // #2410 shipped both of these behaviours untested; the suite it cited as
  // verification predates them and exercises neither.
  describe("key redaction and empty-message fallback (#2410)", () => {
    const GEMINI_KEY = "AIza+needs/encoding=";

    it("redacts the percent-encoded key when an upstream error quotes the request URL", async () => {
      // Gemini's key rides in the URL via encodeURIComponent, so a provider
      // error echoing that URL carries the ENCODED key — a literal
      // split(rawKey) misses it entirely.
      const encoded = encodeURIComponent(GEMINI_KEY);
      fetchMock.mockResolvedValueOnce(
        jsonFetchResponse(
          { error: { message: `bad request for models?key=${encoded}` } },
          400,
        ),
      );

      const res = await onRequestPost(
        request({ "x-byok-key": GEMINI_KEY, "x-byok-provider": "gemini" }),
      );

      const body = (await res.json()) as { error: string };
      expect(body.error).not.toContain(encoded);
      expect(body.error).not.toContain(GEMINI_KEY);
      expect(body.error).toBe("bad request for models?key=[redacted]");
    });

    it("falls back to the status text when the provider's error message is empty", async () => {
      // sanitizeUpstreamError("") returns "" — not nullish — so a `??` here
      // would ship {"ok":false,"error":""} instead of the HTTP-status text.
      fetchMock.mockResolvedValueOnce(jsonFetchResponse({ error: { message: "" } }, 503));

      const res = await onRequestPost(
        request({ "x-byok-key": "sk-or-realkey", "x-byok-provider": "openrouter" }),
      );

      const body = await res.json();
      expect(body).toEqual({ ok: false, error: "OpenRouter returned HTTP 503" });
    });

    it("falls back to 'Request failed' when a thrown error carries an empty message", async () => {
      fetchMock.mockRejectedValueOnce(new Error(""));

      const res = await onRequestPost(
        request({ "x-byok-key": "sk-or-realkey", "x-byok-provider": "openrouter" }),
      );

      expect(res.status).toBe(500);
      const body = await res.json();
      expect(body).toEqual({ ok: false, error: "Request failed" });
    });
  });

  describe("existing providers are unaffected", () => {
    it("calls Gemini with x-goog-api-key header, not a query-string key (#2408)", async () => {
      fetchMock.mockResolvedValueOnce(jsonFetchResponse({}));

      await onRequestPost(
        request({ "x-byok-key": "AIza-realkey", "x-byok-provider": "gemini" }),
      );

      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("https://generativelanguage.googleapis.com/v1beta/models");
      expect(url).not.toContain("key=");
      expect((init.headers as Record<string, string>)["x-goog-api-key"]).toBe("AIza-realkey");
    });

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

    it("returns the caller's catalog model for OpenRouter and Gemini", async () => {
      fetchMock.mockResolvedValue(jsonFetchResponse({}));

      const openrouter = await onRequestPost(
        request({
          "x-byok-key": "sk-or-realkey",
          "x-byok-provider": "openrouter",
          "x-byok-model": "google/gemini-2.0-flash",
        }),
      );
      expect(await openrouter.json()).toEqual({ ok: true, model: "google/gemini-2.0-flash" });

      const gemini = await onRequestPost(
        request({
          "x-byok-key": "AIza-realkey",
          "x-byok-provider": "gemini",
          "x-byok-model": "gemini/gemini-2.5-pro",
        }),
      );
      expect(await gemini.json()).toEqual({ ok: true, model: "gemini/gemini-2.5-pro" });
    });

    it("falls back to the catalog's first model when the caller sends none", async () => {
      fetchMock.mockResolvedValue(jsonFetchResponse({}));

      const openrouter = await onRequestPost(
        request({ "x-byok-key": "sk-or-realkey", "x-byok-provider": "openrouter" }),
      );
      expect((await openrouter.json()).model).toBe("openai/gpt-4o-mini");

      const gemini = await onRequestPost(
        request({ "x-byok-key": "AIza-realkey", "x-byok-provider": "gemini" }),
      );
      const body = await gemini.json();
      expect(body.model).toBe("gemini/gemini-2.0-flash");
      expect(body.model).not.toBe("gemini-2.5-flash");
    });

    it("ignores a requested model that is not in that provider's catalog", async () => {
      fetchMock.mockResolvedValueOnce(jsonFetchResponse({}));
      const res = await onRequestPost(
        request({
          "x-byok-key": "sk-or-realkey",
          "x-byok-provider": "openrouter",
          "x-byok-model": "meta-llama/llama-3.3-70b-instruct",
        }),
      );
      expect((await res.json()).model).toBe("openai/gpt-4o-mini");
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
