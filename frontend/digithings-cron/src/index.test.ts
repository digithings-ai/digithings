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
        cron: "5 22 * * *",
        scheduledTime: Date.UTC(2026, 8, 4, 22, 5),
      } as ScheduledController,
      env,
      executionContext(pending),
    );

    expect(pending).toHaveLength(1);
    await expect(pending[0]).rejects.toThrow(/HTTP 403/);
  });
});
