// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The page-load warm-up gate keeps polling until the services answer ready and
 * releases the loader the moment they do (t1711u).
 *
 * The bug: a probe that started while the stack was booting could take ~50s on
 * the server (auth then assistant, 25s timeouts each) and still answer
 * "waking" after the boot finished, and the client had no timeout of its own,
 * so the loader sat on that stale answer while a refresh loaded at once. And
 * after a 120s budget the gate stopped polling for good. All network is mocked.
 */

type Answer = { ready: boolean } | "hang";

function warmupFetch(script: (call: number) => Answer) {
  let calls = 0;
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const answer = script(calls++);
    if (!String(input).includes("/api/embed/warmup")) throw new Error("unexpected fetch");
    if (answer === "hang") {
      return new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    }
    const services = answer.ready
      ? { auth: "ready", assistant: "ready" }
      : { auth: "waking", assistant: "waking" };
    return Promise.resolve(
      new Response(JSON.stringify({ ready: answer.ready, services }), {
        headers: { "content-type": "application/json" },
      }),
    );
  });
  return { fetchMock, calls: () => calls };
}

async function loadGate() {
  vi.resetModules();
  return import("@/lib/warmup-gate");
}

function phase(): string | undefined {
  return document.documentElement.dataset.digichatWarmup;
}

beforeEach(() => {
  vi.useFakeTimers();
  delete document.documentElement.dataset.digichatWarmup;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("startWarmup", () => {
  it("resolves true on the first ready answer without waiting", async () => {
    const { fetchMock } = warmupFetch(() => ({ ready: true }));
    vi.stubGlobal("fetch", fetchMock);
    const { startWarmup } = await loadGate();

    await expect(startWarmup()).resolves.toBe(true);
    expect(phase()).toBe("ready");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not wait on a probe that hangs: it aborts it and the next probe releases the loader", async () => {
    // First probe hangs (the stale ~50s server answer), the services are ready by the second.
    const { fetchMock } = warmupFetch((n) => (n === 0 ? "hang" : { ready: true }));
    vi.stubGlobal("fetch", fetchMock);
    const { startWarmup } = await loadGate();

    let settled: boolean | undefined;
    void startWarmup().then((v) => (settled = v));
    await vi.advanceTimersByTimeAsync(9_999);
    expect(settled).toBeUndefined();
    // 10s probe timeout, then 1s backoff, then the ready probe.
    await vi.advanceTimersByTimeAsync(1 + 1_000);
    expect(settled).toBe(true);
    expect(phase()).toBe("ready");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBeInstanceOf(AbortSignal);
  });

  it("backs off between waking answers (1s, 1.5s, 2.25s, ... capped at 5s)", async () => {
    const { fetchMock } = warmupFetch(() => ({ ready: false }));
    vi.stubGlobal("fetch", fetchMock);
    const { startWarmup } = await loadGate();

    void startWarmup();
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const at: number[] = [];
    let seen = 1;
    for (let t = 1; t <= 30_000; t += 50) {
      await vi.advanceTimersByTimeAsync(50);
      if (fetchMock.mock.calls.length > seen) {
        seen = fetchMock.mock.calls.length;
        at.push(t);
      }
    }
    const gaps = at.map((t, i) => t - (i === 0 ? 0 : at[i - 1]!));
    // Within one 50ms step of 1000, 1500, 2250, 3375, 5000, 5000, ...
    const want = [1_000, 1_500, 2_250, 3_375, 5_000, 5_000];
    want.forEach((w, i) => expect(Math.abs(gaps[i]! - w)).toBeLessThanOrEqual(50));
    expect(Math.max(...gaps)).toBeLessThanOrEqual(5_050);
  });

  it("past the budget reveals (false) but keeps polling, and flips to ready when the services answer", async () => {
    let readyNow = false;
    const { fetchMock } = warmupFetch(() => ({ ready: readyNow }));
    vi.stubGlobal("fetch", fetchMock);
    const { startWarmup, ensureWarm } = await loadGate();

    let settled: boolean | undefined;
    void startWarmup().then((v) => (settled = v));
    await vi.advanceTimersByTimeAsync(120_000);
    expect(settled).toBe(false);
    expect(phase()).toBe("error");

    // Still polling after the budget: the status stays "slow" until ready.
    const before = fetchMock.mock.calls.length;
    await vi.advanceTimersByTimeAsync(10_000);
    expect(fetchMock.mock.calls.length).toBeGreaterThan(before);
    expect(phase()).toBe("error");

    readyNow = true;
    await vi.advanceTimersByTimeAsync(5_000);
    expect(phase()).toBe("ready");

    // A send right after does not wait or re-probe.
    const calls = fetchMock.mock.calls.length;
    await ensureWarm();
    expect(fetchMock.mock.calls.length).toBe(calls);
  });

  it("shares one polling loop between concurrent callers", async () => {
    const { fetchMock } = warmupFetch((n) => ({ ready: n >= 2 }));
    vi.stubGlobal("fetch", fetchMock);
    const { startWarmup, ensureWarm } = await loadGate();

    const a = startWarmup();
    const b = ensureWarm();
    await vi.advanceTimersByTimeAsync(3_000);
    await expect(a).resolves.toBe(true);
    await expect(b).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
