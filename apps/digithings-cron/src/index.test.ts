import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "./index";
import type { Env } from "./env";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function executionContext(promises: Promise<unknown>[]): ExecutionContext {
  return {
    waitUntil(promise: Promise<unknown>) {
      promises.push(promise);
    },
  } as unknown as ExecutionContext;
}

describe("scheduled", () => {
  it("lets dispatch failures reject through waitUntil", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("forbidden", { status: 403 })),
    );
    const pending: Promise<unknown>[] = [];
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };

    await worker.scheduled(
      {
        // token-canary stays workflow_dispatch. smoke-site is a probe and
        // treats HTTP 403 as a warning, so it cannot prove a dispatch failure.
        cron: "41 6 * * *",
        scheduledTime: Date.UTC(2026, 8, 4, 6, 17),
      } as ScheduledController,
      env,
      executionContext(pending),
    );

    expect(pending).toHaveLength(1);
    await expect(pending[0]).rejects.toThrow(/HTTP 403/);
  });

  it("dispatches Monday house-run-09 to digiquant-runner", async () => {
    const githubFetch = vi.fn();
    vi.stubGlobal("fetch", githubFetch);
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-house", status: "accepted" }, { status: 202 }),
    );
    const pending: Promise<unknown>[] = [];
    const scheduledTime = Date.UTC(2026, 9, 5, 9, 17);
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      RUNNER_AUTH_TOKEN: "runner-token",
      GITHUB_OVERRIDE_JOBS: "",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    await worker.scheduled(
      { cron: "17 9 * * MON", scheduledTime } as ScheduledController,
      env,
      executionContext(pending),
    );
    await Promise.all(pending);

    expect(githubFetch).not.toHaveBeenCalled();
    expect(runnerFetch).toHaveBeenCalledOnce();
  });

  it("does not dispatch disabled daily house-run retries", async () => {
    const githubFetch = vi.fn();
    vi.stubGlobal("fetch", githubFetch);
    const runnerFetch = vi.fn();
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      RUNNER_AUTH_TOKEN: "runner-token",
      GITHUB_OVERRIDE_JOBS: "",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    for (const cron of ["17 10 * * *", "17 11 * * *", "17 12 * * *"]) {
      const pending: Promise<unknown>[] = [];
      await worker.scheduled(
        { cron, scheduledTime: Date.UTC(2026, 9, 5, 10, 17) } as ScheduledController,
        env,
        executionContext(pending),
      );
      await Promise.all(pending);
      expect(pending).toHaveLength(0);
    }

    expect(githubFetch).not.toHaveBeenCalled();
    expect(runnerFetch).not.toHaveBeenCalled();
  });

  // DIG-732: before this, an unmapped cron was one console.error line that
  // nobody read. A trigger that fires with nothing behind it is deployment
  // drift, so the tick must open an issue on the twelve-x path under the
  // unrecognised-cron label — never the missing-required-trigger label, which
  // means the opposite (a required cron is gone).
  it("raises the unrecognised-cron alarm when a tick maps to no job", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        // The alarm searches open issues for this class first, so the stub
        // answers that search honestly: nothing open yet.
        if (String(url).includes("/issues?")) return Response.json([], { status: 200 });
        const status = String(url).includes("/labels/") ? 200 : 201;
        return new Response(JSON.stringify({ html_url: "https://example.test/1" }), {
          status,
          headers: { "content-type": "application/json" },
        });
      }),
    );
    const pending: Promise<unknown>[] = [];
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "github-token" };

    await worker.scheduled(
      { cron: "13 4 * * *", scheduledTime: Date.UTC(2026, 8, 5, 4, 13) } as ScheduledController,
      env,
      executionContext(pending),
    );
    await Promise.all(pending);

    const issues = calls.filter((call) => call.url.endsWith("/issues"));
    expect(issues).toHaveLength(1);
    expect(issues[0].url).toBe("https://api.github.com/repos/digithings-ai/twelve-x/issues");
    const body = JSON.parse(String(issues[0].init?.body)) as {
      title: string;
      labels: string[];
      body: string;
    };
    expect(body.labels).toEqual(["cron-unrecognised-trigger"]);
    expect(body.title).toBe("Unrecognised cron trigger — 13 4 * * *");
    expect(body.body).toContain("13 4 * * *");
    // Only the issue write: an unmapped tick dispatches nothing.
    expect(calls.filter((call) => call.url.includes("/dispatches"))).toHaveLength(0);
  });

  it("opens one issue for six ticks of the same unmapped trigger, not six issues", async () => {
    // The flood this stops: an unmapped `13 4 * * *` (or any high-rate
    // trigger) is re-detected on every tick it fires. One open issue for the
    // drift is an alarm; six is the twelve-x #322 incident by another route.
    // This drives the real scheduled() path, not raiseViolationAlarms directly,
    // because the flood is a property of the tick, not of the alarm function.
    const created: string[] = [];
    let openIssues: { title: string; html_url: string }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (String(url).includes("/issues?")) return Response.json(openIssues, { status: 200 });
        if (String(url).includes("/labels/")) return new Response("{}", { status: 200 });
        if (String(url).endsWith("/issues")) {
          const body = JSON.parse(String(init?.body ?? "{}")) as { title: string };
          const html_url = `https://github.com/digithings-ai/twelve-x/issues/${7000 + created.length}`;
          created.push(body.title);
          openIssues = [...openIssues, { title: body.title, html_url }];
          return Response.json({ html_url }, { status: 201 });
        }
        return new Response("unexpected", { status: 500 });
      }),
    );
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "github-token" };

    for (let tick = 0; tick < 6; tick += 1) {
      const pending: Promise<unknown>[] = [];
      await worker.scheduled(
        {
          cron: "*/10 * * * *",
          scheduledTime: Date.UTC(2026, 8, 5, 4, 0, tick * 10),
        } as ScheduledController,
        env,
        executionContext(pending),
      );
      await Promise.all(pending);
    }

    expect(created).toEqual(["Unrecognised cron trigger — */10 * * * *"]);
  });

  it("dispatches checkpoint-archive to digiquant-runner", async () => {
    const githubFetch = vi.fn();
    vi.stubGlobal("fetch", githubFetch);
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-archive", status: "accepted" }, { status: 202 }),
    );
    const pending: Promise<unknown>[] = [];
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      RUNNER_AUTH_TOKEN: "runner-token",
      GITHUB_OVERRIDE_JOBS: "",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    await worker.scheduled(
      { cron: "30 13 * * *", scheduledTime: Date.UTC(2026, 9, 5, 13, 30) } as ScheduledController,
      env,
      executionContext(pending),
    );
    await Promise.all(pending);

    expect(githubFetch).not.toHaveBeenCalled();
    expect(runnerFetch).toHaveBeenCalledOnce();
  });
});

/**
 * Fake START_COUNTER namespace backed by one Map. Every stub talks to the same
 * store, which is what makes a claim by a second `scheduled()` call visible to
 * the first — the cross-invoke guarantee the real Durable Object provides.
 */
function startCounter() {
  const store = new Map<string, string>();
  const events: string[] = [];
  let sequence = 0;
  const slotId = (key: string, slot: string) => `${key}@${slot}`;
  const stub = {
    async claimSlot(key: string, slot: string) {
      events.push(`claim:${key}@${slot}`);
      const id = slotId(key, slot);
      if (store.has(id)) return null;
      const token = `token-${++sequence}`;
      store.set(id, token);
      return token;
    },
    async markDispatching(key: string, slot: string, token: string) {
      events.push(`dispatching:${key}@${slot}`);
      return store.get(slotId(key, slot)) === token;
    },
    async confirmSlot(key: string, slot: string, token: string) {
      events.push(`confirm:${key}@${slot}`);
      if (store.get(slotId(key, slot)) === token) store.set(slotId(key, slot), "confirmed");
    },
    async releaseSlot(key: string, slot: string, token: string) {
      events.push(`release:${key}@${slot}`);
      if (store.get(slotId(key, slot)) === token) store.delete(slotId(key, slot));
    },
  };
  const namespace = {
    idFromName: (name: string) => name,
    get: () => stub,
  } as unknown as DurableObjectNamespace;
  return { namespace, store, events, stub };
}

describe("scheduled tick idempotency (DIG-4384)", () => {
  // Cloudflare delivers a cron tick at least once. On 14-17 Oct 2026 it
  // delivered every tick of this Worker twice, 7-29s apart, each copy with its
  // own scheduledDatetime (e.g. 00:52:48 and 00:52:55). Both copies reached
  // dispatch, so every workflow started twice. The slot is the cron's minute,
  // not the delivery second: the two copies must share one claim.
  it("dispatches once when the same tick is delivered twice", async () => {
    const githubFetch = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", githubFetch);
    const { namespace, events } = startCounter();
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      START_COUNTER: namespace,
    };

    for (const second of [48, 55]) {
      const pending: Promise<unknown>[] = [];
      await worker.scheduled(
        {
          // token-canary, one of the rows observed dispatching twice.
          cron: "41 6 * * *",
          scheduledTime: Date.UTC(2026, 9, 15, 6, 41, second),
        } as ScheduledController,
        env,
        executionContext(pending),
      );
      await Promise.all(pending);
    }

    expect(githubFetch).toHaveBeenCalledOnce();
    // Without the confirm the claim expires after its lease and the second
    // delivery takes the slot again, so this assertion is part of the pin.
    expect(events.some((event) => event.startsWith("confirm:"))).toBe(true);
  });

  it("uses the cron minute, so a pair straddling a minute boundary is the known limit", async () => {
    // 0 of 514 measured duplicate pairs straddled a minute. If that changes,
    // the slot unit has to change with it: for an every-minute clock a copy at
    // :00:05 cannot be told apart from the next legitimate tick, so this test
    // records the limit instead of pretending it is covered.
    const githubFetch = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", githubFetch);
    const { namespace } = startCounter();
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      START_COUNTER: namespace,
    };

    for (const scheduledTime of [
      Date.UTC(2026, 9, 15, 6, 41, 58),
      Date.UTC(2026, 9, 15, 6, 42, 5),
    ]) {
      const pending: Promise<unknown>[] = [];
      await worker.scheduled(
        { cron: "41 6 * * *", scheduledTime } as ScheduledController,
        env,
        executionContext(pending),
      );
      await Promise.all(pending);
    }

    expect(githubFetch).toHaveBeenCalledTimes(2);
  });

  it("still dispatches the next tick of the same row", async () => {
    const githubFetch = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", githubFetch);
    const { namespace } = startCounter();
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      START_COUNTER: namespace,
    };

    // A claim belongs to one slot, never to the row: the hourly rows must keep
    // firing every hour.
    for (const hour of [6, 7]) {
      const pending: Promise<unknown>[] = [];
      await worker.scheduled(
        {
          cron: "17 * * * *",
          scheduledTime: Date.UTC(2026, 9, 15, hour, 17, 0),
        } as ScheduledController,
        env,
        executionContext(pending),
      );
      await Promise.all(pending);
    }

    expect(githubFetch).toHaveBeenCalledTimes(2);
  });

  it("claims by job, so two rows firing in one minute both dispatch", async () => {
    // production-deploy-gate-watchdog (`17,47 * * * *`) and datatap-answer-check
    // (`17 * * * *`) both fire at :17. They are different jobs, and the shared
    // workflow-file case works the same way: market_context_ingest.yml is
    // dispatched by three rows with three ids.
    const githubFetch = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", githubFetch);
    const { namespace, events } = startCounter();
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      START_COUNTER: namespace,
    };

    for (const cron of ["17,47 * * * *", "17 * * * *"]) {
      const pending: Promise<unknown>[] = [];
      await worker.scheduled(
        { cron, scheduledTime: Date.UTC(2026, 9, 15, 0, 17, 0) } as ScheduledController,
        env,
        executionContext(pending),
      );
      await Promise.all(pending);
    }

    expect(githubFetch).toHaveBeenCalledTimes(2);
    // Pin the key shape as well: the id is in the claim, so a row that shares
    // a workflow file with another row still gets its own start.
    expect(events).toContain(
      "claim:17,47 * * * *\nproduction-deploy-gate-watchdog@2026-10-15T00:17",
    );
    expect(events).toContain("claim:17 * * * *\ndatatap-answer-check@2026-10-15T00:17");
  });

  it("releases the claim when the dispatch fails, so a retry can still start the run", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("forbidden", { status: 403 })),
    );
    const { namespace, events } = startCounter();
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      START_COUNTER: namespace,
    };

    const first: Promise<unknown>[] = [];
    await worker.scheduled(
      { cron: "41 6 * * *", scheduledTime: Date.UTC(2026, 9, 15, 6, 41, 48) } as ScheduledController,
      env,
      executionContext(first),
    );
    await expect(first[0]).rejects.toThrow(/HTTP 403/);
    expect(events.some((event) => event.startsWith("release:"))).toBe(true);

    // The second delivery of the same slot finds the key free and dispatches.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 204 })),
    );
    const second: Promise<unknown>[] = [];
    await worker.scheduled(
      { cron: "41 6 * * *", scheduledTime: Date.UTC(2026, 9, 15, 6, 41, 55) } as ScheduledController,
      env,
      executionContext(second),
    );
    expect(second).toHaveLength(1);
    await expect(second[0]).resolves.toBeDefined();
  });

  it("fails open when the counter binding is absent, never dropping a tick", async () => {
    const githubFetch = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", githubFetch);
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "github-token" };

    for (const second of [48, 55]) {
      const pending: Promise<unknown>[] = [];
      await worker.scheduled(
        {
          cron: "41 6 * * *",
          scheduledTime: Date.UTC(2026, 9, 15, 6, 41, second),
        } as ScheduledController,
        env,
        executionContext(pending),
      );
      await Promise.all(pending);
    }

    expect(githubFetch).toHaveBeenCalledTimes(2);
  });

  it("fails open when the counter namespace throws, never dropping a tick", async () => {
    const githubFetch = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", githubFetch);
    // idFromName succeeds and get throws: the new Error path is synchronous,
    // before the claim's own await, and must still be caught.
    const namespace = {
      idFromName: (name: string) => name,
      get: () => {
        throw new Error("namespace unavailable");
      },
    } as unknown as DurableObjectNamespace;
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "github-token", START_COUNTER: namespace };

    for (const second of [48, 55]) {
      const pending: Promise<unknown>[] = [];
      await worker.scheduled(
        {
          cron: "41 6 * * *",
          scheduledTime: Date.UTC(2026, 9, 15, 6, 41, second),
        } as ScheduledController,
        env,
        executionContext(pending),
      );
      await Promise.all(pending);
    }

    expect(githubFetch).toHaveBeenCalledTimes(2);
  });
});

const WINTER_BEFORE_OPEN = Date.UTC(2026, 0, 15, 13, 40, 0);

function kick(body: unknown, secret = "kick-secret"): Request {
  return new Request("https://digithings-cron/kick", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${secret}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

describe("POST /kick", () => {
  it("skips the winter at-open cron before 09:30 ET", async () => {
    vi.spyOn(Date, "now").mockReturnValue(WINTER_BEFORE_OPEN);
    const runnerFetch = vi.fn();
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const res = await worker.fetch(
      kick({ cron: "40 13 * * MON-FRI" }),
      env,
      executionContext([]),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as { started: string[]; skipped: string[]; runs: unknown[] };
    expect(body.skipped).toEqual(["prices-at-open-13"]);
    expect(body.started).toEqual([]);
    expect(body.runs).toEqual([]);
    expect(runnerFetch).not.toHaveBeenCalled();
  });

  it("force starts the winter at-open cron and returns the run id", async () => {
    vi.spyOn(Date, "now").mockReturnValue(WINTER_BEFORE_OPEN);
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-open", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const res = await worker.fetch(
      kick({ cron: "40 13 * * MON-FRI", force: true }),
      env,
      executionContext([]),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      runs: { job_id: string; run_id: string; status: string }[];
    };
    expect(body.runs).toEqual([
      { job_id: "prices-at-open-13", run_id: "run-open", status: "accepted" },
    ]);
  });

  it("strips privileged house args from a kick without force", async () => {
    vi.spyOn(Date, "now").mockReturnValue(Date.UTC(2026, 8, 30, 10, 0));
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-house", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(
      kick({
        cron: "17 9 * * MON",
        args: {
          refresh_scope: "all",
          dry_run: "true",
          resume_run_id: "prior-run",
          run_date: "2026-09-29",
        },
      }),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    const [, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { args: Record<string, string> };
    expect(body.args).toEqual({
      refresh_scope: "none",
      run_date: "2026-09-30",
    });
  });

  it("keeps privileged house args and marks a forced kick", async () => {
    vi.spyOn(Date, "now").mockReturnValue(Date.UTC(2026, 8, 30, 10, 0));
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-house", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(
      kick({
        cron: "17 9 * * MON",
        force: true,
        args: {
          refresh_scope: "all",
          dry_run: "true",
          resume_run_id: "prior-run",
          run_date: "2026-09-29",
        },
      }),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    const [, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { args: Record<string, string> };
    expect(body.args).toEqual({
      refresh_scope: "all",
      dry_run: "true",
      resume_run_id: "prior-run",
      run_date: "2026-09-29",
      force: "true",
    });
  });

  it("kick without force strips dry_run", async () => {
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-archive", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(
      kick({
        cron: "30 13 * * *",
        args: { dry_run: "true" },
      }),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    const [, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { args: Record<string, string> };
    expect(body.args).toEqual({});
  });

  // --- DIG-47.10 contract. Committed by the planner; these are the failing
  // tests the brief names. Do not edit them — make them pass.

  it("A.4 two kicks with the same startKey create one run", async () => {
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-house", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "s3cret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const kickExplicit = () =>
      worker.fetch(
        kick({ cron: "17 9 * * MON", startKey: "house-run-09:fixed" }, "s3cret"),
        env,
        executionContext([]),
      );

    const first = await kickExplicit();
    expect(first.status).toBe(200);
    expect(((await first.json()) as { started: string[] }).started).toEqual(["house-run-09"]);

    const second = await kickExplicit();
    expect(second.status).toBe(200);
    // The second kick resolves to the same start key, so it is a duplicate and
    // must not reach the runner.
    expect(runnerFetch).toHaveBeenCalledTimes(1);
  });

  it("a keyless kick still works, because four runbooks call it that way", async () => {
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-house", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "s3cret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(
      kick({ cron: "17 9 * * MON" }, "s3cret"),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true });
  });

  it("a non-numeric scheduledTime is rejected, never coerced to NaN", async () => {
    const env: Env = { DRY_RUN: "0", CRON_KICK_SECRET: "s3cret" };

    const res = await worker.fetch(
      kick({ cron: "17 9 * * MON", scheduledTime: "soon" }, "s3cret"),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(400);
    expect(((await res.json()) as { error: string }).error).toBe("invalid_args");
  });

  it("A.5 a keyless kick sends a minute-aligned scheduled time", async () => {
    // The 56_789 ms offset is deliberate and load-bearing. Every other clock in
    // this file is minute-aligned, so the floor under test is the identity on
    // all of them. Do not tidy this offset to match its neighbours: the guard
    // below turns that into a loud failure instead of a silent no-op.
    const requestedAt = Date.UTC(2026, 8, 30, 10, 37, 56, 789);
    expect(requestedAt % 60_000).not.toBe(0);
    // Also guard the hour: minute 37 is what distinguishes this floor from a
    // floor-to-the-hour, which would land on the same minute-aligned instant
    // and pass every assertion below.
    expect(Math.floor(requestedAt / 3_600_000) * 3_600_000).not.toBe(
      Math.floor(requestedAt / 60_000) * 60_000,
    );
    vi.spyOn(Date, "now").mockReturnValue(requestedAt);
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-kick", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(kick({ cron: "17 9 * * MON" }), env, executionContext([]));

    expect(res.status).toBe(200);
    const [, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { scheduled_time: number };
    // A.5 — a keyless kick derives its start from the request time floored to
    // the wall-clock minute, so a repeat inside the same minute collides on
    // purpose. A kick is a deliberately distinct namespace from the cron
    // path: it does not resolve to the cron's firing slot. See DIG-47 spec
    // section 9, decision D3.
    expect(body.scheduled_time % 60_000).toBe(0);
    expect(body.scheduled_time).toBe(Math.floor(requestedAt / 60_000) * 60_000);
  });

  it("kick with force keeps dry_run true", async () => {
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-archive", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(
      kick({
        cron: "30 13 * * *",
        force: true,
        args: { dry_run: "true" },
      }),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    const [, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { args: Record<string, string> };
    expect(body.args.dry_run).toBe("true");
  });

  it("kick does not drop args on a workflow_dispatch row", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      GH_DISPATCH_TOKEN: "token",
      GITHUB_OVERRIDE_JOBS: "twelve-x-market-context-daily",
    };

    const res = await worker.fetch(
      kick({ cron: "30 5 * * *", args: { bucket: "weekly" } }),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain(
      "/repos/digithings-ai/twelve-x/actions/workflows/market_context_ingest.yml/dispatches",
    );
    expect(JSON.parse(String(init.body)).inputs).toEqual({ bucket: "weekly" });
  });

  it("kick carries a caller-supplied run_date onto the twelve-x backfill row", async () => {
    // DIG-1335 (CTO verdict on DIG-1272): a run_date given to the Worker must
    // arrive as an input on the dispatched workflow_dispatch run. Today the
    // row does not exist, so the kick maps to no job and dispatches nothing.
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      GH_DISPATCH_TOKEN: "token",
    };

    const res = await worker.fetch(
      kick({ cron: "41 3 * * *", args: { run_date: "2026-10-05" } }),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain(
      "/repos/digithings-ai/twelve-x/actions/workflows/daily_run.yml/dispatches",
    );
    expect(JSON.parse(String(init.body)).inputs).toEqual({ run_date: "2026-10-05" });
  });

  it("kick without args derives run_date for the twelve-x backfill row", async () => {
    // Same row, no caller date: the Worker stamps the scheduled day instead
    // of dispatching inputs {} (the Oct-6 defect shape: date dropped on floor).
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      GH_DISPATCH_TOKEN: "token",
    };

    const res = await worker.fetch(
      kick({ cron: "41 3 * * *", scheduledTime: Date.UTC(2026, 9, 15, 3, 41) }),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body)).inputs).toEqual({ run_date: "2026-10-15" });
  });
  it("answers 400 when GitHub refuses an undeclared workflow input", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            message: 'Unexpected inputs provided to workflow: ["bucket"]',
          }),
          { status: 422 },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      GH_DISPATCH_TOKEN: "github-token",
      GITHUB_OVERRIDE_JOBS: "twelve-x-market-context-daily",
    };

    // twelve-x-market-context-daily is the only row on this cron. It is kind
    // twelvex, and GITHUB_OVERRIDE_JOBS sends it back to workflow_dispatch.
    // GitHub refusing "bucket" is still the shape of that fallback.
    const res = await worker.fetch(kick({ cron: "30 5 * * *" }), env, executionContext([]));

    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string; cron: string; detail: string };
    expect(body.error).toBe("undeclared_workflow_input");
    expect(body.cron).toBe("30 5 * * *");
    expect(body.detail).toContain("market_context_ingest.yml");
    expect(body.detail).toContain("bucket");
  });
});

describe("GET /runs", () => {
  it("proxies to the runner with RUNNER_AUTH_TOKEN", async () => {
    const runnerFetch = vi.fn(async () => Response.json({ run_id: "run-1", status: "running" }));
    const env: Env = {
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const res = await worker.fetch(
      new Request("https://digithings-cron/runs/run-1", {
        headers: { Authorization: "Bearer kick-secret" },
      }),
      env,
      executionContext([]),
    );
    expect(res.status).toBe(200);
    const [url, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://digiquant-runner/v1/jobs/run-1");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer runner-token");
  });

  it("hides the route when CRON_KICK_SECRET is unset", async () => {
    const res = await worker.fetch(
      new Request("https://digithings-cron/runs/run-1"),
      {},
      executionContext([]),
    );
    expect(res.status).toBe(404);
  });
});
