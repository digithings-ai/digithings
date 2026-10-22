/**
 * DIG-4928: the twelvex-runner Durable Object answers a container hop that
 * rejects with a value that is not an Error.
 *
 * The production failure (2026-10-21): the hop to the container rejected with
 * a Date instance, not an Error. The @cloudflare/containers package rethrows
 * such a value verbatim from its proxy catch, so it left the Durable Object as
 * an uncaught exception and the platform recorded it with `String(value)`: the
 * whole error text of the row was a bare date, and no guard ever saw it.
 *
 * The Worker's own guard sits DOWNSTREAM of the Durable Object (Worker ->
 * stub), so it cannot stop a value from leaving the Durable Object. The guard
 * belongs here, where the hop happens.
 *
 * The Container base class is not constructible outside the Workers runtime
 * (it needs a Durable Object context), so the base is replaced by a stub
 * whose `containerFetch` is the injected mock — the same split
 * digichat-cloudflare/src/index.test.ts uses.
 */
import { describe, expect, it, vi } from "vitest";
import { DURABLE_OBJECT_UNAVAILABLE } from "@digithings/durable-object-reconnect";
import type { Env } from "./env";
import { RUNNER_UNAVAILABLE_DETAIL, TwelveXRunnerContainer } from "./runner";

const hooks = vi.hoisted(() => ({
  containerFetch: vi.fn<(request: Request) => Promise<Response>>(),
}));

vi.mock("@cloudflare/containers", () => {
  class Container<E = unknown> {
    envVars: Record<string, string> = {};
    constructor(
      readonly ctx: unknown,
      readonly env: E,
    ) {}
    async containerFetch(request: Request): Promise<Response> {
      return hooks.containerFetch(request);
    }
  }
  return {
    Container,
    ContainerProxy: class {},
    getContainer: () => undefined,
    getRandom: () => 0,
    loadBalance: () => 0,
    outboundParams: () => ({}),
    switchPort: () => undefined,
  };
});

/** The Durable Object, on the stub base: the hop to the container is the mock. */
function newContainer(): TwelveXRunnerContainer {
  return new TwelveXRunnerContainer(
    {} as DurableObjectState<{}>,
    {} as Env,
  );
}

function runRequest(): Request {
  return new Request("https://twelvex-runner/run/heartbeat", { method: "POST" });
}

describe("TwelveXRunnerContainer.fetch when the container hop rejects with a value that is not an Error", () => {
  it("answers 503 with Retry-After instead of letting the value escape", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    hooks.containerFetch.mockReset();
    hooks.containerFetch.mockRejectedValue(new Date("2026-10-21T11:51:44.000Z"));
    const res = await newContainer().fetch(runRequest());
    spy.mockRestore();

    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe("30");
    expect(await res.json()).toEqual({
      error: DURABLE_OBJECT_UNAVAILABLE,
      detail: RUNNER_UNAVAILABLE_DETAIL,
    });
    // The request is not replayed: a value that came out of the hop says
    // nothing about whether it reached the container, so a second attempt
    // could run the job twice.
    expect(hooks.containerFetch).toHaveBeenCalledTimes(1);
  });

  it("answers 503 for a value that cannot be described", async () => {
    // The description of the cause runs INSIDE the catch, so a description
    // that throws would turn a caught failure back into an uncaught one.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    hooks.containerFetch.mockReset();
    hooks.containerFetch.mockRejectedValue({
      toString() {
        throw new Error("no");
      },
    });
    const res = await newContainer().fetch(runRequest());
    spy.mockRestore();

    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({
      error: DURABLE_OBJECT_UNAVAILABLE,
      detail: RUNNER_UNAVAILABLE_DETAIL,
    });
  });

  it("answers 503 for a value that cannot be inspected", async () => {
    // `instanceof` walks the prototype chain, and a revoked proxy throws
    // there, so the guard that asks the question is asked in a way that
    // cannot throw.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    hooks.containerFetch.mockReset();
    const revoked = Proxy.revocable({}, {});
    revoked.revoke();
    hooks.containerFetch.mockRejectedValue(revoked.proxy);
    const res = await newContainer().fetch(runRequest());
    spy.mockRestore();

    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({
      error: DURABLE_OBJECT_UNAVAILABLE,
      detail: RUNNER_UNAVAILABLE_DETAIL,
    });
  });

  it("rethrows a real Error unchanged", async () => {
    // A real error carries a message, a stack and a type: the caller has to
    // see it, so it is not swallowed by the guard.
    hooks.containerFetch.mockReset();
    const boom = new Error("container /run HTTP 500");
    hooks.containerFetch.mockRejectedValue(boom);
    await expect(newContainer().fetch(runRequest())).rejects.toBe(boom);
  });

  it("serves the container's own answer untouched", async () => {
    hooks.containerFetch.mockReset();
    hooks.containerFetch.mockResolvedValue(new Response("served", { status: 200 }));
    const res = await newContainer().fetch(runRequest());
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("served");
  });
});
