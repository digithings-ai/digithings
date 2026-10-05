import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "./index";
import type { Env } from "./env";
import type { BackfillLedger, LedgerSplit } from "./backfill-do";

/** In-memory stand-in for the Durable Object, addressed by binding. */
class FakeLedger {
  records = new Map<string, "in_flight" | "done">();

  async claim(dates: string[], _now: string, force: boolean): Promise<LedgerSplit> {
    const toDispatch: string[] = [];
    const skipped: string[] = [];
    for (const date of dates) {
      const state = this.records.get(date);
      if (state === undefined || (force && state === "done")) {
        this.records.set(date, "in_flight");
        toDispatch.push(date);
      } else {
        skipped.push(date);
      }
    }
    return { toDispatch, skipped };
  }

  async markDone(dates: string[], _now: string): Promise<void> {
    for (const date of dates) {
      if (this.records.get(date) !== undefined) this.records.set(date, "done");
    }
  }

  async release(dates: string[]): Promise<void> {
    for (const date of dates) {
      if (this.records.get(date) === "in_flight") this.records.delete(date);
    }
  }
}

const SECRET = "kick-secret";

/** Same shape as the existing suite's helper; POST /backfill never waitUntil()s. */
function executionContext(): ExecutionContext {
  return { waitUntil() {} } as unknown as ExecutionContext;
}

function env(over: Partial<Env> = {}): Env {
  return {
    CRON_KICK_SECRET: SECRET,
    BACKFILL_ENABLED: "1",
    GH_DISPATCH_TOKEN: "gh-token",
    ...over,
  } as Env;
}

function withLedger(e: Env): { env: Env; ledger: FakeLedger } {
  const ledger = new FakeLedger();
  const ns = {
    idFromName: () => "backfill-ledger",
    get: () => ledger,
  } as unknown as DurableObjectNamespace;
  return { env: { ...e, BACKFILL_LEDGER: ns }, ledger };
}

function postBackfill(body: unknown, e: Env, auth = true): Promise<Response> {
  return worker.fetch(
    new Request("https://cron.example/backfill", {
      method: "POST",
      headers: auth ? { Authorization: `Bearer ${SECRET}` } : {},
      body: typeof body === "string" ? body : JSON.stringify(body),
    }),
    e,
    executionContext(),
  );
}

/** Spy on every outbound fetch; the Worker must not call api.github.com. */
function spyFetch() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : String(input);
    if (url.includes("api.github.com")) {
      // 204 forbids a body, so pass null rather than "".
      return new Response(null, { status: 204 });
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("POST /backfill — the guard ladder", () => {
  it("404s when no kick secret is configured", async () => {
    const res = await postBackfill({ dates: "2026-06-02" }, env({ CRON_KICK_SECRET: undefined }));
    expect(res.status).toBe(404);
  });

  it("401s a bad bearer", async () => {
    const res = await postBackfill({ dates: "2026-06-02" }, env(), false);
    expect(res.status).toBe(401);
  });

  it("404s while BACKFILL_ENABLED is not 1", async () => {
    const res = await postBackfill({ dates: "2026-06-02" }, env({ BACKFILL_ENABLED: "0" }));
    expect(res.status).toBe(404);
    expect(await res.json()).toMatchObject({ error: "backfill_disabled" });
  });

  it("404s when BACKFILL_ENABLED is unset entirely", async () => {
    const res = await postBackfill({ dates: "2026-06-02" }, env({ BACKFILL_ENABLED: undefined }));
    expect(res.status).toBe(404);
  });

  it("400s a bare kick and never calls api.github.com", async () => {
    const fetchSpy = spyFetch();
    const { env: e, ledger } = withLedger(env());
    const res = await postBackfill({}, e);
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ error: "missing_required_arg" });
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(ledger.records.size).toBe(0);
  });

  it("400s run_date without reaching upstream", async () => {
    const fetchSpy = spyFetch();
    const { env: e } = withLedger(env());
    const res = await postBackfill({ dates: "2026-06-02", run_date: "2026-06-02" }, e);
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ error: "unexpected_arg" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("400s since/until without reaching upstream", async () => {
    const fetchSpy = spyFetch();
    const { env: e } = withLedger(env());
    const res = await postBackfill({ since: "2026-06-02" }, e);
    expect(res.status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("400s a date that is not a real calendar day", async () => {
    const fetchSpy = spyFetch();
    const { env: e } = withLedger(env());
    const res = await postBackfill({ dates: "2026-02-30" }, e);
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ error: "invalid_dates" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("400s a non-JSON body", async () => {
    const res = await postBackfill("{nope", env());
    expect(res.status).toBe(400);
    expect(await res.json()).toMatchObject({ error: "invalid_json" });
  });

  it("503s rather than dispatching without a ledger", async () => {
    const fetchSpy = spyFetch();
    // Without the binding, idempotence is not enforced — so refuse rather than
    // dispatch a backfill the ledger cannot record.
    const res = await postBackfill({ dates: "2026-06-02" }, env());
    expect(res.status).toBe(503);
    expect(await res.json()).toMatchObject({ error: "backfill_unconfigured" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("POST /backfill — dispatch", () => {
  it("dispatches maintenance.yml with backfill_snapshots and the dates", async () => {
    const fetchSpy = spyFetch();
    const { env: e } = withLedger(env());
    const res = await postBackfill({ dates: "2026-06-02,2026-06-03" }, e);

    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({
      ok: true,
      dispatched: ["2026-06-02", "2026-06-03"],
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      "https://api.github.com/repos/digithings-ai/twelve-x/actions/workflows/maintenance.yml/dispatches",
    );
    expect(JSON.parse(String(init.body))).toEqual({
      ref: "develop",
      inputs: { backfill_snapshots: "true", dates: "2026-06-02,2026-06-03" },
    });
  });

  it("accepts a newline-separated remediation list and dispatches it as dates", async () => {
    const fetchSpy = spyFetch();
    const { env: e } = withLedger(env());
    const res = await postBackfill({ dates: "2026-06-02\n2026-06-03" }, e);

    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({
      ok: true,
      dispatched: ["2026-06-02", "2026-06-03"],
    });
    // Upstream still receives one comma-separated `dates` input, never two keys.
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body)).inputs).toEqual({
      backfill_snapshots: "true",
      dates: "2026-06-02,2026-06-03",
    });
  });

  it("sends no run_date, which maintenance.yml does not declare", async () => {
    const fetchSpy = spyFetch();
    const { env: e } = withLedger(env());
    await postBackfill({ dates: "2026-06-02" }, e);
    const body = JSON.parse(String((fetchSpy.mock.calls[0] as [string, RequestInit])[1].body));
    expect(Object.keys(body.inputs)).toEqual(["backfill_snapshots", "dates"]);
    expect(body.inputs).not.toHaveProperty("run_date");
  });

  it("dispatches only the stale dates on a partially remediated list", async () => {
    spyFetch();
    const { env: e, ledger } = withLedger(env());
    await postBackfill({ dates: "2026-06-02" }, e);
    const res = await postBackfill({ dates: "2026-06-02,2026-06-03" }, e);
    expect(await res.json()).toMatchObject({
      dispatched: ["2026-06-03"],
      skipped: ["2026-06-02"],
    });
    expect(ledger.records.get("2026-06-02")).toBe("done");
  });
});

describe("POST /backfill — idempotence per date", () => {
  it("makes a repeat dispatch for a remediated date a no-op, not a rewrite", async () => {
    const fetchSpy = spyFetch();
    const { env: e, ledger } = withLedger(env());

    const first = await postBackfill({ dates: "2026-06-02" }, e);
    expect(first.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    const second = await postBackfill({ dates: "2026-06-02" }, e);
    expect(second.status).toBe(200);
    expect(await second.json()).toMatchObject({
      ok: true,
      dispatched: [],
      already_remediated: true,
    });
    // The whole point: the second dispatch made no upstream request at all.
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(ledger.records.get("2026-06-02")).toBe("done");
  });

  it("re-dispatches a remediated date when force_dates is true", async () => {
    const fetchSpy = spyFetch();
    const { env: e } = withLedger(env());
    await postBackfill({ dates: "2026-06-02" }, e);
    const res = await postBackfill({ dates: "2026-06-02", force_dates: "true" }, e);
    expect(await res.json()).toMatchObject({ dispatched: ["2026-06-02"] });
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it("records nothing and calls nothing on a DRY_RUN preview", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const { env: e, ledger } = withLedger(env({ DRY_RUN: "1" }));
    const res = await postBackfill({ dates: "2026-06-02" }, e);

    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ dry_run: true, dispatched: [] });
    // A preview must not mark the date remediated, or the real dispatch later
    // would skip it forever.
    expect(ledger.records.has("2026-06-02")).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();

    // The same date is still dispatchable for real afterwards — the preview
    // left no trace in the ledger.
    const live = withLedger(env({ DRY_RUN: "0" }));
    const fetchSpy2 = spyFetch();
    const real = await postBackfill({ dates: "2026-06-02" }, live.env);
    expect(real.status).toBe(200);
    expect(await real.json()).toMatchObject({ dispatched: ["2026-06-02"] });
    expect(fetchSpy2).toHaveBeenCalledTimes(1);
  });
});

describe("POST /backfill — failure handling", () => {
  it("502s and releases the claim when GitHub refuses", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("no such workflow", { status: 404 }),
    );
    const { env: e, ledger } = withLedger(env());
    const res = await postBackfill({ dates: "2026-06-02" }, e);

    expect(res.status).toBe(502);
    expect(await res.json()).toMatchObject({ error: "dispatch_failed" });
    // Claim released, so the same date is retryable rather than stuck in flight.
    expect(ledger.records.has("2026-06-02")).toBe(false);
    fetchSpy.mockRestore();
  });

  it("treats an already-queued 422 as success and records the date", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("Workflow is already running", { status: 422 }));
    const { env: e, ledger } = withLedger(env());
    const res = await postBackfill({ dates: "2026-06-02" }, e);

    expect(res.status).toBe(200);
    expect(ledger.records.get("2026-06-02")).toBe("done");
    fetchSpy.mockRestore();
  });
});

describe("POST /backfill — it is not a clock", () => {
  it("has no route other than an explicit POST", async () => {
    const res = await worker.fetch(
      new Request("https://cron.example/backfill"),
      env(),
      executionContext(),
    );
    expect(res.status).toBe(404);
  });

  it("leaves the existing surfaces untouched", async () => {
    const res = await worker.fetch(
      new Request("https://cron.example/healthz"),
      env(),
      executionContext(),
    );
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true, service: "digithings-cron" });
  });
});
