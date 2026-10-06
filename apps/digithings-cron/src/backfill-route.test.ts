import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "./index";
import type { Env } from "./env";
import type {
  BackfillLedger,
  LedgerSplit,
  RemediationRecord,
  RemediationState,
} from "./backfill-do";
import { isStaleClaim } from "./backfill-do";

/**
 * In-memory stand-in for the Durable Object, addressed by binding. It mirrors the
 * real claim rules (three states, in-flight age-out, force only over `done`) so a
 * route test cannot pass against ledger semantics the worker does not have. Name
 * a write in `failOnce` to make it reject, which is how the ledger-error paths
 * are reached at all.
 */
class FakeLedger {
  records = new Map<string, RemediationRecord>();
  failOnce = new Set<"markDone" | "markSuppressed" | "release">();

  private fault(op: "markDone" | "markSuppressed" | "release"): void {
    if (this.failOnce.delete(op)) throw new Error(`ledger ${op} failed`);
  }

  async status(dates: string[]): Promise<Record<string, RemediationState | "unknown">> {
    const out: Record<string, RemediationState | "unknown"> = {};
    for (const date of dates) out[date] = this.records.get(date)?.state ?? "unknown";
    return out;
  }

  async claim(dates: string[], now: string, force: boolean): Promise<LedgerSplit> {
    const toDispatch: string[] = [];
    const skipped: string[] = [];
    const nowMs = Date.parse(now);
    for (const date of dates) {
      const existing = this.records.get(date);
      const claimable =
        existing === undefined ||
        existing.state === "dispatch_suppressed" ||
        (existing.state === "in_flight" && isStaleClaim(existing, nowMs)) ||
        (force && existing.state === "done");
      if (!claimable) {
        skipped.push(date);
        continue;
      }
      this.records.set(date, { state: "in_flight", claimed_at: now });
      toDispatch.push(date);
    }
    return { toDispatch, skipped };
  }

  async markDone(dates: string[], now: string): Promise<void> {
    this.fault("markDone");
    for (const date of dates) {
      const record = this.records.get(date);
      if (record) this.records.set(date, { ...record, state: "done", completed_at: now });
    }
  }

  async markSuppressed(dates: string[], now: string, githubStatus: number): Promise<void> {
    this.fault("markSuppressed");
    for (const date of dates) {
      const record = this.records.get(date);
      if (record) {
        this.records.set(date, {
          ...record,
          state: "dispatch_suppressed",
          suppressed_at: now,
          github_status: githubStatus,
        });
      }
    }
  }

  async release(dates: string[]): Promise<void> {
    this.fault("release");
    for (const date of dates) {
      if (this.records.get(date)?.state === "in_flight") this.records.delete(date);
    }
  }
}

const SECRET = "kick-secret";

/**
 * GitHub's 422 body for a `workflow_dispatch` against a workflow disabled with
 * `disabled_manually`, captured live on 2026-10-06 from a throwaway repo whose
 * only workflow was `workflow_dispatch`-only — the same dispatch against that
 * workflow while enabled answers 204. twelve-x `maintenance.yml` is in exactly
 * this state (DIG-757).
 *
 * Pinned verbatim because the distinction is load-bearing and easy to document
 * wrongly: this is a 422 like any other, but it is *not* one of the bodies
 * `isBenign422` matches ("already queued" / "already running"), so it does not
 * become `dispatch_suppressed`. It is a dispatch failure — 502, claim released.
 * Both outcomes leave the date dispatchable; only the status differs.
 */
const DISABLED_WORKFLOW_422 = JSON.stringify({
  message: "Cannot trigger a 'workflow_dispatch' on a disabled workflow",
  documentation_url:
    "https://docs.github.com/rest/actions/workflows#create-a-workflow-dispatch-event",
  status: "422",
});

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

/** Answer every api.github.com dispatch with one status/body, counting the calls. */
function githubAnswers(status: number, body = "") {
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : String(input);
    if (url.includes("api.github.com")) {
      // 204 forbids a body, so pass null rather than "".
      return new Response(body || null, { status });
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
  return spy;
}

/** A claim stranded by a request that never settled, aged past the in-flight window. */
function strandedLedger(e: Env, date: string) {
  const { env, ledger } = withLedger(e);
  ledger.records.set(date, {
    state: "in_flight",
    claimed_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
  });
  return { env, ledger };
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
    expect(ledger.records.get("2026-06-02")).toMatchObject({ state: "done" });
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
    expect(ledger.records.get("2026-06-02")).toMatchObject({ state: "done" });
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
    expect(await res.json()).toMatchObject({ error: "dispatch_failed", release_failed: false });
    // Claim released, so the same date is retryable rather than stuck in flight.
    expect(ledger.records.has("2026-06-02")).toBe(false);
    fetchSpy.mockRestore();
  });

  it("still 502s, and says so, when the release of a failed dispatch also fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("boom", { status: 404 }));
    const { env: e, ledger } = withLedger(env());
    ledger.failOnce.add("release");
    const res = await postBackfill({ dates: "2026-06-02" }, e);

    // A throwing release used to replace the 502 with an unhandled 500. The
    // claim strands as in_flight and ages out via IN_FLIGHT_TTL_MS; the caller
    // is told the ledger is behind rather than handed a bare failure.
    expect(res.status).toBe(502);
    expect(await res.json()).toMatchObject({ error: "dispatch_failed", release_failed: true });
    expect(ledger.records.get("2026-06-02")).toMatchObject({ state: "in_flight" });
  });

  it("409s a benign 422 and does not call the date remediated", async () => {
    const fetchSpy = githubAnswers(422, "Workflow is already running");
    const { env: e, ledger } = withLedger(env());
    const res = await postBackfill({ dates: "2026-06-02" }, e);

    // GitHub started no run, so this is not remediation and must not be reported
    // as one: 200 here is what let a later retry answer "already remediated" for
    // a date that was never backfilled.
    expect(res.status).toBe(409);
    expect(await res.json()).toMatchObject({
      error: "dispatch_suppressed",
      github_status: 422,
      dispatched: [],
      states: { "2026-06-02": "dispatch_suppressed" },
    });
    expect(ledger.records.get("2026-06-02")).toMatchObject({
      state: "dispatch_suppressed",
      github_status: 422,
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("backfills a suppressed date once the workflow is dispatchable again", async () => {
    githubAnswers(422, "Workflow is already running");
    const { env: e, ledger } = withLedger(env());
    expect((await postBackfill({ dates: "2026-06-02" }, e)).status).toBe(409);

    // DIG-757 re-enables maintenance.yml: the retry is a real dispatch, not a
    // no-op claiming the date was already handled.
    const live = githubAnswers(204);
    live.mockClear(); // the same global spy, now answering 204 only
    const res = await postBackfill({ dates: "2026-06-02" }, e);

    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({
      ok: true,
      dispatched: ["2026-06-02"],
      states: { "2026-06-02": "done" },
    });
    expect(live).toHaveBeenCalledTimes(1);
  });

  it("502s a disabled workflow's 422 instead of reporting it suppressed", async () => {
    const fetchSpy = githubAnswers(422, DISABLED_WORKFLOW_422);
    const { env: e, ledger } = withLedger(env());
    const res = await postBackfill({ dates: "2026-06-02" }, e);

    // The state a disabled maintenance.yml actually produces. It is a 422, but
    // `isBenign422` does not recognise its body, so the dispatch failed rather
    // than being suppressed — which is why the docs used to claim 409 here.
    // What matters is what it is NOT: never `done`, so no later POST can answer
    // "already remediated" for a date twelve-x never backfilled.
    expect(res.status).toBe(502);
    const body = (await res.json()) as Record<string, unknown>;
    expect(body).toMatchObject({ error: "dispatch_failed", release_failed: false });
    expect(body.error).not.toBe("dispatch_suppressed");
    // Nothing recorded at all — in particular not `done`, so no later POST can
    // answer "already remediated" for a date twelve-x never backfilled.
    expect(ledger.records.has("2026-06-02")).toBe(false);

    // One upstream call, not three: this is a refusal, not a rate limit.
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("releases the claim on a disabled workflow, so re-enabling it retries for real", async () => {
    githubAnswers(422, DISABLED_WORKFLOW_422);
    const { env: e, ledger } = withLedger(env());
    expect((await postBackfill({ dates: "2026-06-02" }, e)).status).toBe(502);

    // The 502 released the claim, so the date is claimable again — this is what
    // keeps a disabled workflow from costing a date. DIG-757 re-enables it and
    // the retry is a real dispatch, not a no-op claiming the date was handled.
    expect(ledger.records.has("2026-06-02")).toBe(false);

    const live = githubAnswers(204);
    live.mockClear();
    const res = await postBackfill({ dates: "2026-06-02" }, e);

    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({
      ok: true,
      dispatched: ["2026-06-02"],
      states: { "2026-06-02": "done" },
    });
    expect(live).toHaveBeenCalledTimes(1);
  });

  it("keeps the claim when markDone fails after GitHub already accepted", async () => {
    const fetchSpy = spyFetch();
    const { env: e, ledger } = withLedger(env());
    ledger.failOnce.add("markDone");
    const res = await postBackfill({ dates: "2026-06-02" }, e);

    // A run exists upstream, so this is terminal: reporting 502 would make the
    // operator retry dates that already ran — the DIG-48 surplus — and releasing
    // the claim is what turns one ledger failure into that surplus.
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({
      ok: true,
      dispatched: ["2026-06-02"],
      github_status: 204,
      ledger_write_failed: true,
    });
    expect(ledger.records.get("2026-06-02")).toMatchObject({ state: "in_flight" });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("reports the per-date state so a stranded claim is visible, not called remediated", async () => {
    const fetchSpy = spyFetch();
    const { env: e } = strandedLedger(env(), "2026-06-02");
    const res = await postBackfill({ dates: "2026-06-02" }, e);

    // Aged out by IN_FLIGHT_TTL_MS, so the date is dispatched again rather than
    // answered "already remediated" with zero upstream calls.
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({
      ok: true,
      dispatched: ["2026-06-02"],
      states: { "2026-06-02": "done" },
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("does not claim already_remediated while a live request holds the date", async () => {
    const fetchSpy = spyFetch();
    const { env: e, ledger } = withLedger(env());
    ledger.records.set("2026-06-02", { state: "in_flight", claimed_at: new Date().toISOString() });
    const res = await postBackfill({ dates: "2026-06-02" }, e);

    // `dispatched: []` with `already_remediated: true` was the false report: an
    // in-flight date has not been remediated, it is merely someone else's turn.
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({
      ok: true,
      dispatched: [],
      already_remediated: false,
      states: { "2026-06-02": "in_flight" },
    });
    expect(fetchSpy).not.toHaveBeenCalled();
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
