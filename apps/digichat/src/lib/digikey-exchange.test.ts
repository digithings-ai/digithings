import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DIGIKEY_BFF_ATTEMPT_TIMEOUT_MS,
  DIGIKEY_BFF_RETRY_BUDGET_MS,
  DIGIKEY_BFF_RETRY_DELAYS_MS,
  DIGIKEY_PREFIX,
  exchangeDigikeyApiKey,
  exchangeDigikeyBffSession,
  isDigikeyApiKeyMaterial,
} from "@/lib/digikey-exchange";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
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
    // 400 is not transient: the exchange must give up after one attempt.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      exchangeDigikeyBffSession("http://digikey", "bff-secret", "acme", "user-1")
    ).resolves.toBeNull();

    expect(fetchMock).toHaveBeenCalledTimes(1);
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
        status: 200,
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

  it("retries a transient 5xx and resolves once digikey answers", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({}) })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: "tok" }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const p = exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1");
    await vi.advanceTimersByTimeAsync(10_000);

    await expect(p).resolves.toEqual({
      accessToken: "tok",
      litellmProxyApiKey: null,
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("retries a rate-limited (429) and a request-timeout (408) response", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 429, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: false, status: 408, json: async () => ({}) })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ access_token: "tok" }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const p = exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1");
    await vi.advanceTimersByTimeAsync(10_000);

    await expect(p).resolves.toEqual({
      accessToken: "tok",
      litellmProxyApiKey: null,
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("gives up after the whole retry schedule", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    const timing: { elapsedMs: number | null } = { elapsedMs: null };
    const startedAt = Date.now();
    const p = exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1").then(
      (value) => {
        timing.elapsedMs = Date.now() - startedAt;
        return value;
      }
    );
    await vi.advanceTimersByTimeAsync(60_000);

    await expect(p).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(7);
    // Every attempt answered immediately, so the wall clock is the sum of the
    // backoff delays and nothing else: 56_000 ms for the seven-attempt
    // schedule. The schedule is pinned here, not just in prose.
    expect(timing.elapsedMs).toBe(56_000);
    expect(timing.elapsedMs).toBeLessThan(DIGIKEY_BFF_RETRY_BUDGET_MS);
  });

  it("pins the retry schedule and the per-attempt abort cap", () => {
    expect(DIGIKEY_BFF_RETRY_DELAYS_MS).toEqual([
      0, 2_000, 4_000, 8_000, 12_000, 15_000, 15_000,
    ]);
    expect(DIGIKEY_BFF_ATTEMPT_TIMEOUT_MS).toBe(30_000);
  });

  it("fails fast on a non-transient status without retrying", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    const p = exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1");
    await vi.advanceTimersByTimeAsync(60_000);

    await expect(p).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("retries a thrown attempt and leaves no abort timer pending", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("digikey unreachable"))
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    const p = exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1");
    await vi.advanceTimersByTimeAsync(5_000);

    await expect(p).resolves.toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // The per-attempt abort timer must be released on every path: an attempt
    // that rejected used to leave its 30s timer pending.
    expect(vi.getTimerCount()).toBe(0);
  });

  it("pins the stated budget of one exchange", () => {
    // The budget bounds the whole retry loop, not each attempt: the loop is
    // abandoned once this much wall clock has passed, and no attempt starts
    // after the budget is spent. It is the time a blocked caller waits, so
    // the number is exported and pinned here instead of being claimed in a
    // comment. This test pins the number; the loop's enforcement of it is
    // pinned by the test below ("gives up exactly at the stated budget").
    expect(DIGIKEY_BFF_RETRY_BUDGET_MS).toBe(100_000);
  });

  it("aborts each attempt and gives up exactly at the stated budget", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(
      (_url: string, init: { signal?: AbortSignal }) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(new Error("aborted"))
          );
        })
    );
    vi.stubGlobal("fetch", fetchMock);

    const timing: { elapsedMs: number | null } = { elapsedMs: null };
    const startedAt = Date.now();
    const p = exchangeDigikeyBffSession(
      "http://digikey",
      "bff",
      "acme",
      "user-1"
    ).then((value) => {
      timing.elapsedMs = Date.now() - startedAt;
      return value;
    });

    await vi.advanceTimersByTimeAsync(DIGIKEY_BFF_RETRY_BUDGET_MS);
    await vi.runAllTimersAsync();

    await expect(p).resolves.toBeNull();
    // Every attempt hangs until its own abort fires, so the budget is spent on
    // three attempts: 30s abort, 2s backoff, 30s abort, 4s backoff, 30s abort
    // = 96s. The fourth iteration sleeps the remaining 4s and then breaks
    // before it starts a fetch, because no budget is left for it.
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(timing.elapsedMs).toBe(DIGIKEY_BFF_RETRY_BUDGET_MS);
  });
});
