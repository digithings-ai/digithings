/**
 * Heartbeat sender cases (§5.3 request, §5.5 recognition, §5.6 backoff):
 * response classification, backoff math, scheduling semantics, body shape,
 * and secret hygiene. No stack — `fetch` is injected.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/deploy-config/loader", () => ({
  getDigichatConfig: vi.fn(() => ({ hosts: {} })),
}));

vi.mock("@/lib/embed-tenants", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/lib/embed-tenants")>();
  return { ...actual, getEmbedTenantRegistry: vi.fn(() => new Map()) };
});

import {
  LICENSE_HEARTBEAT_INTERVAL_MS,
  classifyHeartbeatResponse,
  computeBackoffMs,
  getHeartbeatRuntimeForTests,
  startLicenseHeartbeat,
  stopLicenseHeartbeat,
  type HeartbeatBody,
  type HeartbeatScheduler,
} from "./heartbeat";
import {
  getLicenseState,
  initLicenseStateAtStartup,
  resetLicenseStateForTests,
} from "./state";
import {
  generateTestKeypair,
  mintLicenseJwt,
  validLicensePayload,
} from "./jwt-fixtures";

const ISSUER = "http://127.0.0.1:8005";

describe("classifyHeartbeatResponse (§5.5)", () => {
  it("maps 200 valid / 200 expired", () => {
    expect(classifyHeartbeatResponse(200, { license_status: "valid" })).toEqual({
      outcome: "valid",
    });
    expect(classifyHeartbeatResponse(200, { license_status: "expired" })).toEqual({
      outcome: "expired",
    });
  });

  it("requires BOTH 401 status and a recognized error code to deny", () => {
    expect(
      classifyHeartbeatResponse(401, { error: "license_revoked" }),
    ).toEqual({ outcome: "denied", detail: "heartbeat_deny_revoked" });
    expect(
      classifyHeartbeatResponse(401, { error: "unknown_license" }),
    ).toEqual({ outcome: "denied", detail: "heartbeat_deny_unknown" });
    // Bare / generic 401 from another layer must not latch.
    expect(classifyHeartbeatResponse(401, { error: "unauthorized" })).toEqual({
      outcome: "error",
    });
    expect(classifyHeartbeatResponse(401, {})).toEqual({ outcome: "error" });
    expect(classifyHeartbeatResponse(401, null)).toEqual({ outcome: "error" });
    // Recognized codes on the wrong status must not latch either.
    expect(classifyHeartbeatResponse(403, { error: "license_revoked" })).toEqual({
      outcome: "error",
    });
    expect(classifyHeartbeatResponse(200, { error: "license_revoked" })).toEqual({
      outcome: "error",
    });
  });

  it("treats 404/5xx/malformed bodies as errors (serve + backoff)", () => {
    expect(classifyHeartbeatResponse(404, { error: "not found" })).toEqual({
      outcome: "error",
    });
    expect(classifyHeartbeatResponse(502, "<html>proxy</html>")).toEqual({
      outcome: "error",
    });
    expect(classifyHeartbeatResponse(500, null)).toEqual({ outcome: "error" });
    expect(classifyHeartbeatResponse(200, { license_status: "bogus" })).toEqual({
      outcome: "error",
    });
  });
});

describe("computeBackoffMs (§5.6)", () => {
  const MIN = 60_000;
  it("doubles from 5m and caps at 6h, never past 24h", () => {
    expect(computeBackoffMs(1)).toBe(5 * MIN);
    expect(computeBackoffMs(2)).toBe(10 * MIN);
    expect(computeBackoffMs(3)).toBe(20 * MIN);
    expect(computeBackoffMs(100)).toBe(6 * 60 * MIN);
    expect(computeBackoffMs(100)).toBeLessThanOrEqual(LICENSE_HEARTBEAT_INTERVAL_MS);
  });

  it("applies ±10% jitter, clamped", () => {
    expect(computeBackoffMs(1, 0.1)).toBe(Math.round(5 * MIN * 1.1));
    expect(computeBackoffMs(1, -0.1)).toBe(Math.round(5 * MIN * 0.9));
    expect(computeBackoffMs(1, 5)).toBe(Math.round(5 * MIN * 1.1));
    expect(computeBackoffMs(0)).toBe(5 * MIN);
  });
});

describe("startLicenseHeartbeat scheduling", () => {
  const keys = generateTestKeypair();
  const now = Math.floor(Date.now() / 1000);
  let token: string;
  let logSpy: ReturnType<typeof vi.spyOn>;
  let warnSpy: ReturnType<typeof vi.spyOn>;

  interface FakeTimer {
    cb: () => void;
    ms: number;
    unrefCalled: boolean;
  }

  function fakeScheduler() {
    const intervals: FakeTimer[] = [];
    const timeouts: FakeTimer[] = [];
    const scheduler: HeartbeatScheduler = {
      setInterval: (cb, ms) => {
        const t: FakeTimer = { cb, ms, unrefCalled: false };
        intervals.push(t);
        return { unref: () => { t.unrefCalled = true; } };
      },
      clearInterval: (handle) => {
        const i = intervals.findIndex((t) => t.cb === (handle as { cb: unknown }).cb);
        void i;
      },
      setTimeout: (cb, ms) => {
        const t: FakeTimer = { cb, ms, unrefCalled: false };
        timeouts.push(t);
        return { unref: () => { t.unrefCalled = true; } };
      },
      clearTimeout: () => {},
    };
    return { scheduler, intervals, timeouts };
  }

  function seedValid() {
    resetLicenseStateForTests();
    initLicenseStateAtStartup({
      env: {
        DIGICHAT_LICENSE_JWT: token,
        DIGIKEY_PUBLIC_KEY_PEM: keys.publicKeyPem,
        DIGIKEY_ISSUER: ISSUER,
      } as unknown as NodeJS.ProcessEnv,
      nowSec: now,
    });
    expect(getLicenseState(now).state).toBe("valid");
  }

  beforeEach(() => {
    token = mintLicenseJwt(keys.privateKeyPem);
    logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv("DIGIKEY_URL", "http://127.0.0.1:8005");
  });

  afterEach(() => {
    stopLicenseHeartbeat();
    resetLicenseStateForTests();
    logSpy.mockRestore();
    warnSpy.mockRestore();
    vi.unstubAllEnvs();
  });

  it("uses a 24h constant interval", () => {
    expect(LICENSE_HEARTBEAT_INTERVAL_MS).toBe(24 * 60 * 60 * 1000);
  });

  it("never starts a timer for unlicensed containers", () => {
    resetLicenseStateForTests();
    const { scheduler, intervals } = fakeScheduler();
    startLicenseHeartbeat({ scheduler, fetchFn: vi.fn() as unknown as typeof fetch });
    expect(intervals).toHaveLength(0);
    expect(getHeartbeatRuntimeForTests().running).toBe(false);
  });

  it("does not schedule when DIGIKEY_URL is missing (log once, keep serving)", () => {
    seedValid();
    vi.stubEnv("DIGIKEY_URL", "");
    const { scheduler, intervals } = fakeScheduler();
    const fetchFn = vi.fn() as unknown as typeof fetch;
    startLicenseHeartbeat({ scheduler, fetchFn });
    startLicenseHeartbeat({ scheduler, fetchFn });
    expect(intervals).toHaveLength(0);
    expect(getHeartbeatRuntimeForTests().running).toBe(false);
    expect(getLicenseState(now).state).toBe("valid");
    const warns = warnSpy.mock.calls.map((c) => c.map(String).join(" "));
    expect(warns.filter((l) => l.includes("missing_digikey_url"))).toHaveLength(1);
  });

  it("still reports when expired at boot (identity claims persist)", async () => {
    resetLicenseStateForTests();
    const expired = mintLicenseJwt(
      keys.privateKeyPem,
      validLicensePayload({ exp: Math.floor(Date.now() / 1000) - 3600 }),
    );
    initLicenseStateAtStartup({
      env: {
        DIGICHAT_LICENSE_JWT: expired,
        DIGIKEY_PUBLIC_KEY_PEM: keys.publicKeyPem,
        DIGIKEY_ISSUER: ISSUER,
      } as unknown as NodeJS.ProcessEnv,
    });
    expect(getLicenseState().state).toBe("expired");
    const { scheduler } = fakeScheduler();
    const seen: Array<{ url: string; init: RequestInit }> = [];
    const fetchFn = vi.fn(async (url: string, init: RequestInit) => {
      seen.push({ url, init });
      return new Response(JSON.stringify({ license_status: "expired" }), {
        status: 200,
      });
    });
    startLicenseHeartbeat({
      scheduler,
      fetchFn: fetchFn as unknown as typeof fetch,
      jitterRatio: () => 0,
    });
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1));
    expect(seen[0].url).toBe("http://127.0.0.1:8005/v1/licenses/heartbeat");
    const headers = new Headers(seen[0].init.headers);
    expect(headers.get("authorization")).toBe(`Bearer ${expired}`);
    const body = JSON.parse(String(seen[0].init.body)) as HeartbeatBody;
    expect(body).toMatchObject({
      license_id: "lic-test-001",
      customer: "datatap",
      license_status: "expired",
      seq: 1,
    });
    expect(getLicenseState().state).toBe("expired");
  });

  it("schedules a 24h unref'd interval and fires the first attempt immediately", async () => {
    seedValid();
    const { scheduler, intervals } = fakeScheduler();
    const fetchFn = vi.fn(async () => new Response(JSON.stringify({ license_status: "valid" }), { status: 200 }));
    startLicenseHeartbeat({ scheduler, fetchFn: fetchFn as unknown as typeof fetch });
    expect(intervals).toHaveLength(1);
    expect(intervals[0].ms).toBe(LICENSE_HEARTBEAT_INTERVAL_MS);
    expect(intervals[0].unrefCalled).toBe(true);
    // First attempt is fire-and-forget: flush microtasks and it has run.
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1));
    expect(getHeartbeatRuntimeForTests().seq).toBe(1);
  });

  it("is a no-op when already running; stop clears everything", async () => {
    seedValid();
    const { scheduler, intervals } = fakeScheduler();
    const fetchFn = vi.fn(async () => new Response(JSON.stringify({ license_status: "valid" }), { status: 200 }));
    startLicenseHeartbeat({ scheduler, fetchFn: fetchFn as unknown as typeof fetch });
    startLicenseHeartbeat({ scheduler, fetchFn: fetchFn as unknown as typeof fetch });
    expect(intervals).toHaveLength(1);
    expect(getHeartbeatRuntimeForTests().running).toBe(true);
    stopLicenseHeartbeat();
    expect(getHeartbeatRuntimeForTests().running).toBe(false);
  });

  it("sends the exact body key set with an incrementing seq and Bearer raw JWT", async () => {
    seedValid();
    const { scheduler } = fakeScheduler();
    const seen: Array<{ url: string; init: RequestInit }> = [];
    const fetchFn = vi.fn(async (url: string, init: RequestInit) => {
      seen.push({ url, init });
      return new Response(JSON.stringify({ license_status: "valid" }), { status: 200 });
    });
    startLicenseHeartbeat({
      scheduler,
      fetchFn: fetchFn as unknown as typeof fetch,
      jitterRatio: () => 0,
    });
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1));
    expect(seen[0].url).toBe("http://127.0.0.1:8005/v1/licenses/heartbeat");
    expect(seen[0].init.method).toBe("POST");
    const headers = new Headers(seen[0].init.headers);
    expect(headers.get("authorization")).toBe(`Bearer ${token}`);
    const body = JSON.parse(String(seen[0].init.body)) as HeartbeatBody;
    expect(Object.keys(body).sort()).toEqual(
      ["customer", "hosts_configured", "license_id", "license_status", "seq", "started_at", "version"].sort(),
    );
    expect(body).toMatchObject({
      license_id: "lic-test-001",
      customer: "datatap",
      license_status: "valid",
      seq: 1,
    });
    expect(typeof body.version).toBe("string");
    expect(typeof body.started_at).toBe("string");
  });

  it("serves through 404s and bare 401s, latches on 401 license_revoked", async () => {
    seedValid();
    const { scheduler, timeouts } = fakeScheduler();
    let answer: { status: number; body: unknown } = { status: 404, body: {} };
    const fetchFn = vi.fn(async () => new Response(JSON.stringify(answer.body), { status: answer.status }));
    startLicenseHeartbeat({
      scheduler,
      fetchFn: fetchFn as unknown as typeof fetch,
      jitterRatio: () => 0,
    });
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1));
    // 404 (slice 3 not deployed): serve, state unchanged, backoff scheduled.
    await vi.waitFor(() => expect(timeouts.length).toBeGreaterThan(0));
    expect(getLicenseState(now).state).toBe("valid");

    // Bare 401 from another layer: serve, state unchanged.
    answer = { status: 401, body: { error: "unauthorized" } };
    timeouts[timeouts.length - 1].cb();
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(timeouts.length).toBeGreaterThan(1));
    expect(getLicenseState(now).state).toBe("valid");

    // Recognized deny: latch revoked at this heartbeat.
    answer = { status: 401, body: { error: "license_revoked" } };
    timeouts[timeouts.length - 1].cb();
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(3));
    await vi.waitFor(() =>
      expect(getLicenseState(now)).toMatchObject({
        state: "revoked",
        detail: "heartbeat_deny_revoked",
      }),
    );
  });

  it("never logs the raw JWT or Authorization value", async () => {
    seedValid();
    const { scheduler } = fakeScheduler();
    const fetchFn = vi.fn(async () => new Response(JSON.stringify({ license_status: "valid" }), { status: 200 }));
    startLicenseHeartbeat({ scheduler, fetchFn: fetchFn as unknown as typeof fetch });
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1));
    const logged = [...logSpy.mock.calls, ...warnSpy.mock.calls]
      .map((c) => c.map(String).join(" "))
      .join("\n");
    expect(logged).not.toContain(token);
    expect(logged).not.toContain("Bearer ");
  });

  it("drops a tick that fires while an attempt is in flight", async () => {
    seedValid();
    const { scheduler, intervals } = fakeScheduler();
    let release!: (v: Response) => void;
    const gate = new Promise<Response>((resolve) => { release = resolve; });
    const fetchFn = vi.fn(() => gate);
    startLicenseHeartbeat({ scheduler, fetchFn: fetchFn as unknown as typeof fetch });
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1));
    // Fire the interval tick while the first attempt is still pending.
    intervals[0].cb();
    await Promise.resolve();
    expect(fetchFn).toHaveBeenCalledTimes(1);
    release(new Response(JSON.stringify({ license_status: "valid" }), { status: 200 }));
    await vi.waitFor(() => expect(getHeartbeatRuntimeForTests().seq).toBe(1));
  });
});
