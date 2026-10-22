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
  it("reports a rejected exchange on a non-transient status and posts the bff_session grant", async () => {
    // 400 is not transient: the exchange must give up after one attempt, and
    // it must say the token was refused rather than that digikey is asleep.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      exchangeDigikeyBffSession("http://digikey", "bff-secret", "acme", "user-1")
    ).resolves.toEqual({ ok: false, reason: "rejected", status: 400 });

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
      ok: true,
      exchange: { accessToken: "tok", litellmProxyApiKey: "llmk_abc" },
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
      ok: true,
      exchange: { accessToken: "tok", litellmProxyApiKey: null },
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
      ok: true,
      exchange: { accessToken: "tok", litellmProxyApiKey: null },
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

    // Transient answers all the way through: digikey was cold, not refusing.
    await expect(p).resolves.toEqual({
      ok: false,
      reason: "unreachable",
      status: 500,
    });
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

  it("reports a rejected token on 401 without retrying", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    const p = exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1");
    await vi.advanceTimersByTimeAsync(60_000);

    // digikey answered and refused the token: one attempt, no retry, and the
    // reason says "rejected" so no caller blames the dependency being cold.
    await expect(p).resolves.toEqual({
      ok: false,
      reason: "rejected",
      status: 401,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("tells a cold digikey apart from a rejected token", async () => {
    // The whole point of DIG-4424: the same call, two different digikey
    // behaviours, two different reasons. A sleeping container answers with
    // transient statuses or no answer at all; a refused token answers 401.
    vi.useFakeTimers();

    const coldFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", coldFetch);
    const cold = exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1");
    await vi.advanceTimersByTimeAsync(60_000);
    await expect(cold).resolves.toEqual({
      ok: false,
      reason: "unreachable",
      status: 503,
    });

    const refusedFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", refusedFetch);
    await expect(
      exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1")
    ).resolves.toEqual({ ok: false, reason: "rejected", status: 401 });
    expect(refusedFetch).toHaveBeenCalledTimes(1);
  });

  it("reports an unreachable digikey when every attempt errors", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockRejectedValue(new Error("digikey unreachable"));
    vi.stubGlobal("fetch", fetchMock);

    const p = exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1");
    await vi.advanceTimersByTimeAsync(60_000);

    // No answer at all: the dependency is cold or down. There is no status
    // to report, and the reason must not be "rejected".
    await expect(p).resolves.toEqual({
      ok: false,
      reason: "unreachable",
      status: null,
    });
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

    await expect(p).resolves.toEqual({
      ok: false,
      reason: "rejected",
      status: 401,
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // The per-attempt abort timer must be released on every path: an attempt
    // that rejected used to leave its 30s timer pending.
    expect(vi.getTimerCount()).toBe(0);
  });

  it("treats a 200 without an access_token as a refusal, not as a cold digikey", async () => {
    // digikey answered and issued no token: that is a refusal of the request,
    // not a dependency that never came up.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ litellm_proxy_api_key: "llmk_abc" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1")
    ).resolves.toEqual({ ok: false, reason: "rejected", status: 200 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("treats a 200 with a body that is not JSON as a refusal", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => {
        throw new Error("Unexpected token < in JSON at position 0");
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1")
    ).resolves.toEqual({ ok: false, reason: "rejected", status: 200 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not throw when the token payload has an unusable shape", async () => {
    // A field that is not a string must not throw out of the exchange: it used
    // to escape as a raw TypeError and be answered 502 upstream_auth with the
    // TypeError text in the body.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: 12_345 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1")
    ).resolves.toEqual({ ok: false, reason: "rejected", status: 200 });
  });

  it("keeps a token digikey issued even when the optional litellm key is malformed", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: "tok", litellm_proxy_api_key: { a: 1 } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1")
    ).resolves.toEqual({
      ok: true,
      exchange: { accessToken: "tok", litellmProxyApiKey: null },
    });
  });

  it("lets the last answer win: a transient 503 then a 401 is a refusal", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    const p = exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1");
    await vi.advanceTimersByTimeAsync(5_000);

    // digikey woke up and then refused the token: the refusal is the answer.
    await expect(p).resolves.toEqual({
      ok: false,
      reason: "rejected",
      status: 401,
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("recognises digikey's own answer that its bff_session grant is not configured", async () => {
    // digikey answers 503 {"detail":"bff_session grant not configured
    // (DIGIKEY_BFF_TOKEN)"} when it has no DIGIKEY_BFF_TOKEN in its own env.
    // That is a permanent credential problem on the digikey side, and it
    // shares its status with a waking container, so the answer has to be read
    // to tell the two apart (DIG-4424).
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({}),
      text: async () =>
        JSON.stringify({
          detail: "bff_session grant not configured (DIGIKEY_BFF_TOKEN)",
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1")
    ).resolves.toEqual({ ok: false, reason: "not_configured", status: 503 });
    // Permanent: one attempt, no retry, no wait.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps another transient 503 retryable", async () => {
    // The stack Worker answers a booting container with its own body, which
    // must stay on the retryable side.
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({}),
      text: async () => JSON.stringify({ error: "container_booting" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const p = exchangeDigikeyBffSession("http://digikey", "bff", "acme", "user-1");
    await vi.advanceTimersByTimeAsync(60_000);

    await expect(p).resolves.toEqual({
      ok: false,
      reason: "unreachable",
      status: 503,
    });
    expect(fetchMock).toHaveBeenCalledTimes(7);
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

    await expect(p).resolves.toEqual({
      ok: false,
      reason: "unreachable",
      status: null,
    });
    // Every attempt hangs until its own abort fires, so the budget is spent on
    // three attempts: 30s abort, 2s backoff, 30s abort, 4s backoff, 30s abort
    // = 96s. The fourth iteration sleeps the remaining 4s and then breaks
    // before it starts a fetch, because no budget is left for it.
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(timing.elapsedMs).toBe(DIGIKEY_BFF_RETRY_BUDGET_MS);
  });

  it("shortens the abort window of a late attempt so the budget is not overshot", async () => {
    // The mixed failure pattern: digikey boots slowly (two attempts hang) and
    // then answers with a transient 5xx, so the last attempt starts late. The
    // abort cap is a cap: that late attempt gets min(cap, budget left), not
    // the full cap, so the exchange still fails exactly at the budget instead
    // of running past it.
    vi.useFakeTimers();
    const attempts: { startedAt: number; abortedAt: number | null }[] = [];
    const fetchMock = vi.fn((_url: string, init: { signal?: AbortSignal }) => {
      const attempt = { startedAt: Date.now(), abortedAt: null as number | null };
      attempts.push(attempt);
      if (attempts.length === 3) {
        // The third attempt answers at once with a transient status.
        return Promise.resolve({ ok: false, status: 500, json: async () => ({}) });
      }
      return new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => {
          attempt.abortedAt = Date.now();
          reject(new Error("aborted"));
        });
      });
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
    await vi.advanceTimersByTimeAsync(DIGIKEY_BFF_RETRY_BUDGET_MS + 10_000);
    await vi.runAllTimersAsync();

    // The transient 5xx is remembered, but the reason stays "unreachable":
    // digikey never issued a token.
    await expect(p).resolves.toEqual({
      ok: false,
      reason: "unreachable",
      status: 500,
    });
    // Two hung attempts (30s + 2s + 30s), one fast 5xx, then a fourth attempt
    // that starts with 26_000 ms of budget left.
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(attempts).toHaveLength(4);
    const last = attempts[3];
    // The fake clock starts at the current wall clock, so the attempt times
    // are relative to the moment the exchange was called.
    expect(last.startedAt - startedAt).toBe(74_000);
    const abortedAt = last.abortedAt ?? -1;
    // The late attempt is cut short, and the call fails on the budget itself.
    expect(abortedAt - last.startedAt).toBeLessThan(DIGIKEY_BFF_ATTEMPT_TIMEOUT_MS);
    expect(abortedAt - startedAt).toBe(DIGIKEY_BFF_RETRY_BUDGET_MS);
    expect(timing.elapsedMs).toBe(DIGIKEY_BFF_RETRY_BUDGET_MS);
  });
});
