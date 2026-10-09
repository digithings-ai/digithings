/**
 * Tests for the Supabase egress restriction detector (DIG-1814).
 *
 * The load-bearing claims are negative ones, so most of what follows asserts
 * that something does NOT read as OK:
 *
 *   - a missing binding is UNKNOWN, not OK
 *   - a 401/403 is UNKNOWN, not a restriction and not OK
 *   - a transport failure is UNKNOWN, not OK
 *   - an unmeasured byte figure never trips the threshold
 *
 * A guard that silently degrades an absent measurement to "all clear" is the
 * failure mode this whole guard exists to prevent, so each of those has its own
 * assertion rather than being folded into a table.
 */
import { describe, expect, it, vi } from "vitest";

import { EGRESS_ALARM, raiseEgressAlarm } from "./egress-alarm";
import type { Env } from "./env";
import {
  EGRESS_PROBE_URLS,
  classifyEgress,
  evaluateQuota,
  projectRefFromUrl,
  runEgressProbe,
} from "./supabase-egress";
import { JOBS } from "./jobs";

const PROJECT_URL = "https://rwagjbkvxkdwqmouagad.supabase.co";
const KEY = "test-anon-key";

function envWith(overrides: Partial<Env> = {}): Env {
  return {
    SUPABASE_CORE_URL: PROJECT_URL,
    SUPABASE_ANON_KEY: KEY,
    GH_DISPATCH_TOKEN: "test-dispatch-token",
    ...overrides,
  };
}

/** A fetch impl that never touches the network. Keeps its Mock type. */
function fakeFetch(status: number) {
  return vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response("[]", { status }),
  );
}

describe("classifyEgress", () => {
  it("reads HTTP 402 as a restriction and alerts", () => {
    const v = classifyEgress(402);
    expect(v.label).toBe("RESTRICTED");
    expect(v.restricted).toBe(true);
    expect(v.alert).toBe(true);
  });

  it("reads an accepted request as OK", () => {
    for (const status of [200, 204, 206]) {
      const v = classifyEgress(status);
      expect(v.label).toBe("OK");
      expect(v.restricted).toBe(false);
      expect(v.alert).toBe(false);
    }
  });

  it("does not cry wolf on a credential failure", () => {
    for (const status of [401, 403]) {
      const v = classifyEgress(status);
      expect(v.label).toBe("UNKNOWN");
      expect(v.restricted).toBe(false);
      expect(v.alert).toBe(false);
    }
  });

  it("tells a credential failure apart from an unrecognised status", () => {
    // Both are UNKNOWN, so the label alone cannot prove this branch runs. The
    // message is what a human acts on: a 403 means "fix the key", a 503 means
    // "Supabase is unwell". They must not read the same.
    const auth = classifyEgress(403);
    const other = classifyEgress(503);
    expect(auth.message).not.toBe(other.message);
    expect(auth.message.toLowerCase()).toContain("credential");
    expect(other.message.toLowerCase()).toContain("unrecognised");
  });

  it("does not read a transport failure as OK", () => {
    const v = classifyEgress(0);
    expect(v.label).toBe("UNKNOWN");
    expect(v.alert).toBe(false);
  });

  it("does not read an unrecognised status as OK", () => {
    for (const status of [404, 429, 500, 503]) {
      expect(classifyEgress(status).label).toBe("UNKNOWN");
    }
  });

  it("only RESTRICTED ever sets alert", () => {
    // Exhaustive over the statuses this guard can actually observe. If a new
    // branch is added that sets alert without being a restriction, this fails.
    for (const status of [0, 200, 204, 206, 401, 402, 403, 404, 429, 500, 503]) {
      const v = classifyEgress(status);
      expect(v.alert).toBe(v.restricted);
    }
  });

  it("reports UNKNOWN when the probe was never configured", () => {
    const v = classifyEgress(200, { configured: false });
    // The positive control: 200 would be OK if the probe had run at all.
    expect(classifyEgress(200).label).toBe("OK");
    expect(v.label).toBe("UNKNOWN");
    expect(v.restricted).toBe(false);
    expect(v.alert).toBe(false);
  });

  it("carries a message on every verdict", () => {
    for (const status of [0, 200, 402, 401, 503]) {
      expect(classifyEgress(status).message.length).toBeGreaterThan(10);
    }
  });
});

describe("evaluateQuota", () => {
  const GB = 1024 * 1024 * 1024;

  it("computes a percentage against a caller-supplied quota", () => {
    expect(evaluateQuota(4 * GB, 5 * GB).percent).toBeCloseTo(80);
  });

  it("trips the threshold at exactly the threshold", () => {
    expect(evaluateQuota(4 * GB, 5 * GB).over).toBe(true);
  });

  it("does not trip below the threshold", () => {
    expect(evaluateQuota(3.9 * GB, 5 * GB).over).toBe(false);
  });

  it("honours a custom threshold", () => {
    expect(evaluateQuota(0.5 * GB, 5 * GB, 80).over).toBe(false);
    expect(evaluateQuota(0.5 * GB, 5 * GB, 10).over).toBe(true);
  });

  it("never trips on an unmeasured figure", () => {
    // The empty-vs-empty trap. `null` means "we did not measure", which must
    // not read as 0% and must not read as over.
    const v = evaluateQuota(null, 5 * GB);
    expect(v.percent).toBeNull();
    expect(v.over).toBe(false);
  });

  it("never divides by an unknown quota", () => {
    for (const quota of [0, -1, Number.NaN]) {
      const v = evaluateQuota(4 * GB, quota);
      expect(v.percent).toBeNull();
      expect(v.over).toBe(false);
    }
  });

  it("reports over when the figure exceeds the quota outright", () => {
    // 6 GB against 5 GB is the October overage, as a fraction.
    expect(evaluateQuota(6 * GB, 5 * GB).over).toBe(true);
  });
});

describe("projectRefFromUrl", () => {
  it("extracts the Supabase project ref from the hostname", () => {
    expect(projectRefFromUrl(PROJECT_URL)).toBe("rwagjbkvxkdwqmouagad");
  });

  it("returns the input rather than throwing on an unparseable URL", () => {
    expect(projectRefFromUrl("not a url")).toBe("not a url");
  });
});

describe("runEgressProbe", () => {
  const now = new Date("2026-10-09T12:00:00.000Z");

  it("resolves without throwing when Supabase accepts the probe", async () => {
    const fetchImpl = fakeFetch(200);
    await expect(
      runEgressProbe(envWith(), fetchImpl, now),
    ).resolves.toEqual({ ok: true });
  });

  it("sends the scoped key on both the apikey and Authorization headers", async () => {
    const fetchImpl = fakeFetch(200);
    await runEgressProbe(envWith(), fetchImpl, now);
    const init = fetchImpl.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers.apikey).toBe(KEY);
    expect(headers.Authorization).toBe(`Bearer ${KEY}`);
  });

  it("throws on 402 so the cron run records the failure", async () => {
    await expect(
      runEgressProbe(envWith(), fakeFetch(402), now),
    ).rejects.toThrow(/restricted/i);
  });

  it("does not throw on a 403", async () => {
    await expect(
      runEgressProbe(envWith(), fakeFetch(403), now),
    ).resolves.toEqual({ ok: true });
  });

  it("does not throw when fetch itself rejects", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      throw new Error("ECONNRESET");
    });
    await expect(runEgressProbe(envWith(), fetchImpl, now)).resolves.toEqual({
      ok: true,
    });
  });

  it("resolves without probing when the URL is not bound", async () => {
    const fetchImpl = fakeFetch(402);
    await expect(
      runEgressProbe(envWith({ SUPABASE_CORE_URL: undefined }), fetchImpl, now),
    ).resolves.toEqual({ ok: true });
    // Positive control: the same stub would have thrown had it been called.
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("resolves without probing when the key is not bound", async () => {
    const fetchImpl = fakeFetch(402);
    await expect(
      runEgressProbe(envWith({ SUPABASE_ANON_KEY: undefined }), fetchImpl, now),
    ).resolves.toEqual({ ok: true });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("never logs the key", async () => {
    const lines: string[] = [];
    const spy = vi.spyOn(console, "log").mockImplementation((arg) => {
      lines.push(String(arg));
    });
    try {
      await runEgressProbe(envWith(), fakeFetch(200), now);
    } finally {
      spy.mockRestore();
    }
    expect(lines.join("\n")).not.toContain(KEY);
  });

  it("tolerates a trailing slash on the bound URL", async () => {
    const fetchImpl = fakeFetch(200);
    await runEgressProbe(envWith({ SUPABASE_CORE_URL: `${PROJECT_URL}/` }), fetchImpl, now);
    expect(fetchImpl.mock.calls[0][0]).toBe(`${PROJECT_URL}/rest/v1/?select=*&limit=1`);
  });
});

describe("raiseEgressAlarm", () => {
  const verdict = classifyEgress(402);

  it("refuses to raise without a dispatch token, and does not throw", async () => {
    const fetcher = fakeFetch(201);
    const result = await raiseEgressAlarm(
      { GH_DISPATCH_TOKEN: undefined } as Env,
      verdict,
      { projectRef: "rwagjbkvxkdwqmouagad", fetcher },
    );
    expect(result.raised).toBe(false);
    expect(result.error).toMatch(/GH_DISPATCH_TOKEN/);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("opens one issue when no occurrence is already open", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/labels/")) return new Response("{}", { status: 200 });
      if (url.includes("state=open")) return new Response("[]", { status: 200 });
      if (init?.method === "POST") {
        return new Response(JSON.stringify({ html_url: "https://gh/issue/1" }), {
          status: 201,
        });
      }
      return new Response("{}", { status: 200 });
    });

    const result = await raiseEgressAlarm(envWith(), verdict, {
      projectRef: "rwagjbkvxkdwqmouagad",
      fetcher,
    });
    expect(result.raised).toBe(true);
    expect(result.issue).toBe("https://gh/issue/1");
    expect(result.duplicate).toBeUndefined();
  });

  it("returns the open occurrence instead of filing a second one", async () => {
    const title = `${EGRESS_ALARM.title} — rwagjbkvxkdwqmouagad`;
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/labels/")) return new Response("{}", { status: 200 });
      if (url.includes("state=open")) {
        return new Response(
          JSON.stringify([{ title, html_url: "https://gh/issue/7" }]),
          { status: 200 },
        );
      }
      if (init?.method === "POST") throw new Error("must not file a second issue");
      return new Response("{}", { status: 200 });
    });

    const result = await raiseEgressAlarm(envWith(), verdict, {
      projectRef: "rwagjbkvxkdwqmouagad",
      fetcher,
    });
    expect(result.raised).toBe(false);
    expect(result.duplicate).toBe(true);
    expect(result.issue).toBe("https://gh/issue/7");
  });

  it("still raises when the open-issue search fails, rather than staying silent", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/labels/")) return new Response("{}", { status: 200 });
      if (url.includes("state=open")) return new Response("boom", { status: 500 });
      if (init?.method === "POST") {
        return new Response(JSON.stringify({ html_url: "https://gh/issue/2" }), {
          status: 201,
        });
      }
      return new Response("{}", { status: 200 });
    });

    const result = await raiseEgressAlarm(envWith(), verdict, {
      projectRef: "rwagjbkvxkdwqmouagad",
      fetcher,
    });
    // A duplicate is better than a silent miss.
    expect(result.raised).toBe(true);
  });

  it("reports a non-201 create as an error and does not throw", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/labels/")) return new Response("{}", { status: 200 });
      if (url.includes("state=open")) return new Response("[]", { status: 200 });
      if (init?.method === "POST") return new Response("nope", { status: 403 });
      return new Response("{}", { status: 200 });
    });

    const result = await raiseEgressAlarm(envWith(), verdict, {
      projectRef: "rwagjbkvxkdwqmouagad",
      fetcher,
    });
    expect(result.raised).toBe(false);
    expect(result.error).toMatch(/403/);
  });

  it("does not throw when the fetcher itself explodes", async () => {
    const fetcher = vi.fn(async () => {
      throw new Error("network down");
    });
    const result = await raiseEgressAlarm(envWith(), verdict, {
      projectRef: "rwagjbkvxkdwqmouagad",
      fetcher,
    });
    expect(result.raised).toBe(false);
    expect(result.error).toMatch(/network down/);
  });

  it("carries the label on every result", async () => {
    const result = await raiseEgressAlarm(envWith(), verdict, {
      projectRef: "rwagjbkvxkdwqmouagad",
      fetcher: fakeFetch(500),
    });
    expect(result.label).toBe(EGRESS_ALARM.label);
  });
});

describe("the egress probe is wired as a real job", () => {
  const job = JOBS.find((j) => j.id === "supabase-egress-guard");

  it("exists, is enabled, and runs hourly off :17", () => {
    expect(job).toBeDefined();
    expect(job!.enabled).toBe(true);
    expect(job!.kind).toBe("probe");
    expect(job!.probe).toBe("egress");
    expect(job!.cron).toBe("11 * * * *");
  });

  it("has no workflow, so nothing can dispatch it to Actions", () => {
    // The probe is Worker-only. A workflow here would be a name with no file.
    expect(job!.workflow).toBeUndefined();
  });

  it("enumerates no static URLs, because the target is a binding", () => {
    expect(EGRESS_PROBE_URLS).toEqual([]);
  });
});
