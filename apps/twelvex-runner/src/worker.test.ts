import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";
import { decideAlert, SESSION_LABEL, SOURCE_LABEL, TRANSPORT_LABEL } from "./alerts";
import type { Env } from "./env";
import { handle, type RunResult } from "./worker";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function env(over: Partial<Env> = {}): Env {
  return {
    RUNNER_AUTH_TOKEN: "runner-token",
    GH_ISSUES_TOKEN: "gh-token",
    DRY_RUN: "0",
    TWELVEX_CONTAINER: {} as DurableObjectNamespace,
    ...over,
  };
}

function post(route: string, body: unknown, token = "runner-token"): Request {
  return new Request(`https://twelvex-runner/run/${route}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

function containerResult(over: Partial<RunResult> = {}): RunResult {
  return {
    ok: true,
    exit_code: 0,
    duration_ms: 12,
    log_tail: "",
    dry_run: false,
    command: ["python", "-m", "twelve_x.scripts.primemarket_session_heartbeat"],
    alert: "none",
    ...over,
  };
}

describe("routing and auth", () => {
  it("healthz does not call the container", async () => {
    const container = vi.fn();
    const res = await handle(new Request("https://twelvex-runner/healthz"), env(), {
      fetch: container,
    } as unknown as Fetcher);
    expect(res.status).toBe(200);
    expect(container).not.toHaveBeenCalled();
  });

  it("rejects a missing and a wrong token", async () => {
    const container = vi.fn();
    const binding = { fetch: container } as unknown as Fetcher;
    const missing = await handle(post("heartbeat", {}), env({ RUNNER_AUTH_TOKEN: undefined }), binding);
    const wrong = await handle(post("heartbeat", {}, "other"), env(), binding);
    expect(missing.status).toBe(401);
    expect(wrong.status).toBe(401);
    expect(container).not.toHaveBeenCalled();
  });

  it("rejects an unknown route", async () => {
    const container = vi.fn();
    const res = await handle(post("other", {}), env(), { fetch: container } as unknown as Fetcher);
    expect(res.status).toBe(404);
    expect(container).not.toHaveBeenCalled();
  });

  it("rejects ingest without a known bucket", async () => {
    const container = vi.fn();
    const res = await handle(post("ingest", { bucket: "hourly" }), env(), {
      fetch: container,
    } as unknown as Fetcher);
    expect(res.status).toBe(400);
    expect(container).not.toHaveBeenCalled();
  });

  it("forwards ingest with the workflow bucket and auth", async () => {
    const container = vi.fn(async () => Response.json(containerResult({ exit_code: 0 })));
    const github = vi.fn();
    const res = await handle(
      post("ingest", { job_id: "twelve-x-market-context-daily", bucket: "daily" }),
      env(),
      { fetch: container } as unknown as Fetcher,
      github as unknown as typeof fetch,
    );
    expect(res.status).toBe(200);
    const request = container.mock.calls[0][0] as Request;
    const forwarded = JSON.parse(await request.text()) as { bucket: string; dry_run: boolean };
    expect(forwarded.bucket).toBe("daily");
    expect(forwarded.dry_run).toBe(false);
    expect(github).not.toHaveBeenCalled();
  });

  it("DRY_RUN=1 still calls the container and does not write or alert", async () => {
    const container = vi.fn(async () =>
      Response.json(containerResult({ dry_run: true, log_tail: "dry_run ingest" })),
    );
    const github = vi.fn();
    const res = await handle(post("heartbeat", { job_id: "twelve-x-primemarket-heartbeat" }), env({ DRY_RUN: "1" }), {
      fetch: container,
    } as unknown as Fetcher, github as unknown as typeof fetch);
    expect(res.status).toBe(200);
    const body = (await res.json()) as RunResult;
    expect(body.dry_run).toBe(true);
    expect(body.alert).toBe("none");
    const request = container.mock.calls[0][0] as Request;
    const forwarded = JSON.parse(await request.text()) as { dry_run: boolean };
    expect(forwarded.dry_run).toBe(true);
    expect(github).not.toHaveBeenCalled();
  });
});

describe("alerts", () => {
  it("ingest exit 2 stays quiet and exit 3 uses the transport label", () => {
    expect(
      decideAlert({ route: "ingest", exitCode: 2, reason: "auth", now: 0, open: [] }).action,
    ).toBe("none");
    const transport = decideAlert({
      route: "ingest",
      exitCode: 3,
      bucket: "intraday",
      reason: "timeout",
      now: Date.parse("2026-10-13T00:00:00Z"),
      open: [],
    });
    expect(transport).toMatchObject({ action: "create", label: TRANSPORT_LABEL });
    const source = decideAlert({
      route: "ingest",
      exitCode: 1,
      bucket: "daily",
      reason: "source: dmx",
      now: Date.parse("2026-10-13T00:00:00Z"),
      open: [],
    });
    expect(source).toMatchObject({ action: "create", label: SOURCE_LABEL });
  });

  it("comments inside the 24h window and escalates an unread heartbeat", () => {
    const now = Date.parse("2026-10-13T18:00:00Z");
    const decision = decideAlert({
      route: "heartbeat",
      exitCode: 1,
      reason: "session probe failed",
      now,
      open: [{ number: 270, createdAt: now - 13 * 60 * 60 * 1000, acknowledged: false }],
    });
    expect(decision).toMatchObject({
      action: "comment",
      label: SESSION_LABEL,
      number: 270,
      escalate: true,
    });
  });

  it("closes open session alerts only when the probe passes", () => {
    const now = Date.parse("2026-10-13T06:00:00Z");
    const closed = decideAlert({
      route: "heartbeat",
      exitCode: 0,
      reason: "ok",
      now,
      open: [{ number: 330, createdAt: now - 60_000, acknowledged: false }],
    });
    expect(closed).toMatchObject({ action: "close", numbers: [330], label: SESSION_LABEL });
    const failed = decideAlert({
      route: "heartbeat",
      exitCode: 1,
      reason: "rejected",
      now,
      open: [],
    });
    expect(failed).toMatchObject({ action: "create", label: SESSION_LABEL, assignees: ["chrizefan"] });
  });
});

describe("image pin", () => {
  it("pins the same twelve-x ref in the Dockerfile", () => {
    const ref = readFileSync(path.join(root, "twelvex-ref.txt"), "utf8").trim();
    const dockerfile = readFileSync(path.resolve(root, "../../Dockerfile.twelvex-runner"), "utf8");
    const toml = readFileSync(path.join(root, "wrangler.toml"), "utf8");
    expect(ref).toMatch(/^[0-9a-f]{40}$/);
    expect(dockerfile).toContain(ref);
    expect(toml).toContain('instance_type = "basic"');
    expect(toml).toContain("max_instances = 1");
    expect(dockerfile).not.toMatch(/ghp_|github_pat_/);
  });
});
