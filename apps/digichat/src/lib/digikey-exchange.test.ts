import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DIGIKEY_PREFIX,
  exchangeDigikeyApiKey,
  exchangeDigikeyBffSession,
  isDigikeyApiKeyMaterial,
} from "@/lib/digikey-exchange";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("isDigikeyApiKeyMaterial", () => {
  it("recognizes dgk_live_ material and rejects other bearer shapes", () => {
    expect(isDigikeyApiKeyMaterial(`${DIGIKEY_PREFIX}abc`)).toBe(true);
    expect(isDigikeyApiKeyMaterial("Bearer dgk_live_abc")).toBe(false);
    expect(isDigikeyApiKeyMaterial("sk-openai")).toBe(false);
    expect(isDigikeyApiKeyMaterial("")).toBe(false);
  });
});

describe("exchangeDigikeyApiKey", () => {
  it("returns null when digikey responds non-OK", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) })
    );
    await expect(
      exchangeDigikeyApiKey("http://127.0.0.1:8005/", "dgk_live_x")
    ).resolves.toBeNull();
  });

  it("returns null when access_token is missing or blank", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ access_token: "  " }),
      })
    );
    await expect(
      exchangeDigikeyApiKey("http://127.0.0.1:8005", "dgk_live_x")
    ).resolves.toBeNull();
  });

  it("strips trailing slash on base URL and maps empty litellm key to null", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        access_token: " jwt-token ",
        litellm_proxy_api_key: "  ",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const ex = await exchangeDigikeyApiKey("http://127.0.0.1:8005/", "dgk_live_x");
    expect(ex).toEqual({ accessToken: "jwt-token", litellmProxyApiKey: null });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8005/v1/oauth/token",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ grant_type: "api_key", api_key: "dgk_live_x" }),
      })
    );
  });
});

describe("exchangeDigikeyBffSession", () => {
  it("returns null on failed exchange and posts bff_session grant", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      exchangeDigikeyBffSession("http://digikey", "bff-secret", "acme", "user-1")
    ).resolves.toBeNull();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://digikey/v1/oauth/token",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer bff-secret",
        }),
        body: JSON.stringify({
          grant_type: "bff_session",
          tenant_slug: "acme",
          subject: "user-1",
        }),
      })
    );
  });

  it("forwards litellm_proxy_api_key when digikey returns one", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          access_token: "tok",
          litellm_proxy_api_key: "llmk_abc",
        }),
      })
    );
    await expect(
      exchangeDigikeyBffSession("http://digikey", "bff", "t", "s")
    ).resolves.toEqual({
      accessToken: "tok",
      litellmProxyApiKey: "llmk_abc",
    });
  });
});
