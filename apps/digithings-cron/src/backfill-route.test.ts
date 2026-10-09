import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "./index";
import type { Env } from "./env";
import type { LedgerSplit, RemediationRecord, RemediationState } from "./backfill-do";
import { BackfillLedger } from "./backfill-do";

/** Fake DurableObjectState with a genuinely serialising transaction, as in backfill-do.test.ts. */
function fakeState() {
  const store = new Map<string, unknown>();
  let chain: Promise<unknown> = Promise.resolve();
  const txn = {
    async get<T>(k: string) { return store.get(k) as T | undefined; },
    async put(k: string, v: unknown) { store.set(k, v); },
    async delete(k: string) { store.delete(k); },
  };
  const storage = {
    async get<T>(k: string) { return store.get(k) as T | undefined; },
    async put(k: string, v: unknown) { store.set(k, v); },
    async delete(k: string) { store.delete(k); },
    async transaction<T>(cb: (t: typeof txn) => Promise<T>): Promise<T> {
      const run = chain.then(() => cb(txn));
      chain = run.then(() => undefined, () => undefined);
      return run;
    },
  };
  return { state: { storage } as unknown as DurableObjectState, store };
}

/**
 * Binding shim over the real `BackfillLedger`, so a route test cannot pass
 * against ledger semantics the worker does not have. This harness used to
 * re-implement the claim rules, which is how the two blocking defects below
 * stayed invisible: the fake agreed with a buggy ledger rather than catching it.
 * Name a write in `failOnce` to make it reject, which is how the ledger-error
 * paths are reached at all.
 */
class FakeLedger {
  failOnce = new Set<"markDone" | "markSuppressed" | "release">();

  private readonly state = fakeState();
  private readonly inner = new BackfillLedger(this.state.state, {} as Env);

  private fault(op: "markDone" | "markSuppressed" | "release"): void {
    if (this.failOnce.delete(op)) throw new Error(`ledger ${op} failed`);
  }

  /** Date-keyed view over the ledger's storage, for arranging a precondition. */
  readonly records = (() => {
    const store = this.state.store;
    return {
      set: (date: string, record: RemediationRecord): void => {
        store.set(`backfill:${date}`, record);
      },
      get: (date: string): RemediationRecord | undefined =>
        store.get(`backfill:${date}`) as RemediationRecord | undefined,
      has: (date: string): boolean => store.has(`backfill:${date}`),
      size: (): number => store.size,
    };
  })();

  status(dates: string[]): Promise<Record<string, RemediationState | "unknown">> {
    return this.inner.status(dates);
  }

  async claim(dates: string[], now: string, force: boolean): Promise<LedgerSplit> {
    return this.inner.claim(dates, now, force);
  }

  async markDone(dates: string[], now: string, claimedAt: string): Promise<void> {
    this.fault("markDone");
    await this.inner.markDone(dates, now, claimedAt);
  }

  async markSuppressed(
    dates: string[],
    now: string,
    githubStatus: number,
    claimedAt: string,
  ): Promise<void> {
    this.fault("markSuppressed");
    await this.inner.markSuppressed(dates, now, githubStatus, claimedAt);
  }

  async release(dates: string[], claimedAt: string): Promise<void> {
    this.fault("release");
    await this.inner.release(dates, claimedAt);
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
    expect(ledger.records.size()).toBe(0);
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
    const { env: e } = withLedger(env());
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

describe("POST /backfill — a declined forced re-dispatch is not a surplus", () => {
  /**
   * The three-step sequence, end to end through the route.
   *
   * 1. A plain POST dispatches and GitHub accepts, so the date is remediated.
   * 2. An operator forces the date again while twelve-x maintenance.yml is
   *    disabled, and GitHub answers a benign 422. Nothing ran.
   * 3. A plain POST for the same date must be a no-op.
   *
   * Step 2 used to demote the date to `dispatch_suppressed`, which threw away
   * the fact that step 1 started a real run. Step 3 then re-dispatched it — the
   * DIG-48 surplus. This is reachable today, not hypothetically, precisely
   * because the workflow is disabled and every forced POST takes the 422 branch.
   */
  it("keeps a remediated date remediated when a forced re-dispatch is declined", async () => {
    const fetchSpy = spyFetch();
    const { env: e, ledger } = withLedger(env());

    const first = await postBackfill({ dates: "2026-06-02" }, e);
    expect(first.status).toBe(200);
    expect(ledger.records.get("2026-06-02")).toMatchObject({ state: "done" });

    fetchSpy.mockRestore();
    const declined = githubAnswers(422, "Workflow is already running");
    const forced = await postBackfill({ dates: "2026-06-02", force_dates: "true" }, e);
    expect(forced.status).toBe(409);
    expect(await forced.json()).toMatchObject({ error: "dispatch_suppressed" });
    expect(ledger.records.get("2026-06-02")).toMatchObject({ state: "done" });
    expect(declined).toHaveBeenCalledTimes(1);

    // Step 3: nothing left to do, and nothing is dispatched.
    const third = await postBackfill({ dates: "2026-06-02" }, e);
    expect(third.status).toBe(200);
    expect(await third.json()).toMatchObject({
      ok: true,
      dispatched: [],
      already_remediated: true,
      states: { "2026-06-02": "done" },
    });
    expect(declined).toHaveBeenCalledTimes(1);
  });

  it("keeps a remediated date remediated when the workflow is disabled", async () => {
    // The other decline path, and the one reachable today. GitHub answers 422
    // with "The workflow is not valid" for a disabled workflow, which is not one
    // of dispatch.ts's benign-422 bodies — so the dispatch fails hard and the
    // route releases the claim. Releasing must restore the `done` record rather
    // than deleting it; deleting it leaves the date unknown and the next plain
    // POST dispatches it a second time.
    const fetchSpy = spyFetch();
    const { env: e, ledger } = withLedger(env());

    const first = await postBackfill({ dates: "2026-06-02" }, e);
    expect(first.status).toBe(200);
    expect(ledger.records.get("2026-06-02")).toMatchObject({ state: "done" });

    fetchSpy.mockRestore();
    githubAnswers(422, JSON.stringify({ message: "The workflow is not valid" }));
    const forced = await postBackfill({ dates: "2026-06-02", force_dates: "true" }, e);
    expect(forced.status).toBe(502);
    expect(await forced.json()).toMatchObject({
      error: "dispatch_failed",
      release_failed: false,
    });
    expect(ledger.records.get("2026-06-02")).toMatchObject({ state: "done" });

    const third = await postBackfill({ dates: "2026-06-02" }, e);
    expect(await third.json()).toMatchObject({
      dispatched: [],
      already_remediated: true,
      states: { "2026-06-02": "done" },
    });
  });

  it("still leaves a date that never ran claimable, because nothing ran", async () => {
    // The counterpart, so the fix cannot be "422 always means done": a date that
    // has never been accepted by GitHub has no run behind it and must stay
    // dispatchable once the workflow is enabled again.
    const fetchSpy = spyFetch();
    const { env: e, ledger } = withLedger(env());
    await postBackfill({ dates: "2026-06-02" }, e);
    expect(ledger.records.get("2026-06-02")).toMatchObject({ state: "done" });

    fetchSpy.mockRestore();
    githubAnswers(422, "Workflow is already running");
    // A different date, never dispatched, forced while disabled.
    const declined = await postBackfill({ dates: "2026-06-03", force_dates: "true" }, e);
    expect(declined.status).toBe(409);
    expect(ledger.records.get("2026-06-03")).toMatchObject({
      state: "dispatch_suppressed",
    });

    // The workflow is dispatchable again, so the retry is a real dispatch.
    githubAnswers(204);
    const retried = await postBackfill({ dates: "2026-06-03" }, e);
    expect(retried.status).toBe(200);
    expect(await retried.json()).toMatchObject({
      ok: true,
      dispatched: ["2026-06-03"],
      states: { "2026-06-03": "done" },
    });
  });
});

describe("POST /backfill — a late settle does not touch a re-dispatched date", () => {
  /**
   * A claim that has aged out is re-dispatched by a later request, and that
   * request's markDone must land — the date it settled is the one now on disk.
   * The complementary late-write case (A settling after B re-dispatched) is
   * fenced and asserted in backfill-do.test.ts, where the interleaving can be
   * arranged directly rather than raced through the route.
   */
  it("settles the claim it just took over an aged-out one", async () => {
    const fetchSpy = githubAnswers(204);
    const { env: e, ledger } = withLedger(env());

    // A claim stranded by a request that never settled, aged past the window.
    const stale = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    ledger.records.set("2026-06-02", { state: "in_flight", claimed_at: stale });

    const res = await postBackfill({ dates: "2026-06-02" }, e);
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ dispatched: ["2026-06-02"] });
    expect(ledger.records.get("2026-06-02")).toMatchObject({ state: "done" });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
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
