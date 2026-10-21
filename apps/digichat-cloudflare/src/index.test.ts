import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CONTAINER_UNAVAILABLE_BODY, RETRY_AFTER_SECONDS } from "./container-retry";
import worker, { DigiChatContainer, type Env } from "./index";

/**
 * The Container base class is not constructible outside the Workers runtime
 * (it needs a Durable Object context with a container, a storage and
 * blockConcurrencyWhile), so the base is replaced by a stub whose `fetch` is
 * the injected mock. That is the whole point of these tests: the hop to the
 * container is what fails.
 */
const hooks = vi.hoisted(() => ({
  containerFetch: vi.fn<(request: Request) => Promise<Response>>(),
  getContainer: vi.fn(),
}));

vi.mock("@cloudflare/containers", () => {
  class Container {
    async fetch(request: Request): Promise<Response> {
      return hooks.containerFetch(request);
    }
  }
  return { Container, getContainer: hooks.getContainer };
});

/** What the Worker and the Durable Object logged, one line per call. */
let logged: string[] = [];

/** The Durable Object, on the stub base: the hop to the container is the mock. */
function newContainer(): DigiChatContainer {
  return new DigiChatContainer({} as DurableObjectState<{}>, {});
}

/** A Worker env whose container binding is the stub above. */
function workerEnv(): Env {
  return { DIGICHAT: {} as DurableObjectNamespace<DigiChatContainer> } as Env;
}

function chatRequest(): Request {
  return new Request("https://digithings.ai/api/chat");
}

beforeEach(() => {
  logged = [];
  hooks.containerFetch.mockReset();
  hooks.getContainer.mockReset();
  // The Durable Object logs the tenant source on its first fetch and the
  // failure it catches. Neither is the subject of these tests, but the log is
  // how these tests tell the two paths apart, so it is recorded, not dropped.
  vi.spyOn(console, "log").mockImplementation((...args: unknown[]) => {
    logged.push(args.map((arg) => String(arg)).join(" "));
  });
  vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
    logged.push(args.map((arg) => String(arg)).join(" "));
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DigiChatContainer.fetch when the container hop rejects with a value that is not an Error", () => {
  it("answers 503 with Retry-After instead of letting the value escape", async () => {
    // The @cloudflare/containers package rethrows a non-Error rejection
    // verbatim, so a thrown Date used to leave the Durable Object as an
    // uncaught exception and the Worker's own guard never saw it
    // (run-watch DIG-4928).
    const container = newContainer();
    hooks.containerFetch.mockRejectedValue(new Date("2026-10-21T11:51:44.000Z"));

    const res = await container.fetch(chatRequest());

    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RETRY_AFTER_SECONDS));
    expect(await res.text()).toBe(CONTAINER_UNAVAILABLE_BODY);
  });

  it("rethrows a real error unchanged", async () => {
    const container = newContainer();
    const boom = new Error("boom");
    hooks.containerFetch.mockRejectedValue(boom);

    await expect(container.fetch(chatRequest())).rejects.toBe(boom);
  });
});

describe("the digichat Worker", () => {
  it("sees a response instead of an uncaught exception", async () => {
    const container = newContainer();
    hooks.getContainer.mockReturnValue({
      fetch: (request: Request) => container.fetch(request),
    });
    hooks.containerFetch.mockRejectedValue(new Date("2026-10-21T11:51:44.000Z"));

    const res = await worker.fetch(chatRequest(), workerEnv());

    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RETRY_AFTER_SECONDS));
    expect(await res.text()).toBe(CONTAINER_UNAVAILABLE_BODY);
    // The Durable Object answered, so the Worker never took the path where the
    // container could not be reached at all.
    expect(logged.join("\n")).not.toContain("digichat: container could not be reached");
    // The failure is logged with a description, so the log says what happened
    // instead of holding a bare date.
    expect(logged.join("\n")).toContain("2026");
  });
});
