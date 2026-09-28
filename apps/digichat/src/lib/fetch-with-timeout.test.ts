import { afterEach, describe, expect, it, vi } from "vitest";
import { abortOrMessage, DEFAULT_FETCH_TIMEOUT_MS, fetchWithTimeout } from "./fetch-with-timeout";

describe("fetchWithTimeout", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("resolves normally when fetch resolves before the timeout", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("ok", { status: 200 }));
    const resp = await fetchWithTimeout("https://example.invalid", {});
    expect(resp.status).toBe(200);
  });

  it("aborts and rejects with AbortError when fetch hangs past the timeout", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          const signal = (init as RequestInit)?.signal;
          signal?.addEventListener("abort", () => {
            const err = new Error("The operation was aborted.");
            err.name = "AbortError";
            reject(err);
          });
        }),
    );
    await expect(fetchWithTimeout("https://example.invalid", {}, 5)).rejects.toThrow();
  });
});

describe("abortOrMessage", () => {
  it("formats an AbortError as a timeout message", () => {
    const err = new Error("aborted");
    err.name = "AbortError";
    expect(abortOrMessage(err, DEFAULT_FETCH_TIMEOUT_MS)).toContain("timed out");
  });

  it("passes through a plain Error's message", () => {
    expect(abortOrMessage(new Error("network down"))).toBe("network down");
  });

  it("falls back to a generic message for a non-Error throw", () => {
    expect(abortOrMessage("not an error")).toBe("Unknown error");
  });
});
