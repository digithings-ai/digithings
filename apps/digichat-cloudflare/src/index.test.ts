import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CONTAINER_UNAVAILABLE_BODY, RETRY_AFTER_SECONDS } from "./container-retry";
import worker, { BOOT_CONFIG_TTL_MS, DigiChatContainer, type Env } from "./index";
import { env as stubEnv } from "../test/cloudflare-workers-stub";
import { occInviteCookieValue } from "./occ-gate";

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
  // The package exports more than the two names index.ts uses. They are
  // stubbed here so a future import fails as a type error, not as a
  // confusing "no X export is defined on the mock".
  class ContainerProxy {}
  return {
    Container,
    ContainerProxy,
    getContainer: hooks.getContainer,
    getRandom: () => 0,
    loadBalance: () => 0,
    outboundParams: () => ({}),
    switchPort: () => undefined,
  };
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
    // A subclass, so the check is on `instanceof` and not on the exact class.
    const boom = new TypeError("boom");
    hooks.containerFetch.mockRejectedValue(boom);

    await expect(container.fetch(chatRequest())).rejects.toBe(boom);
  });

  it("answers 503 when the rejection is a value that cannot be inspected", async () => {
    // `instanceof` throws on a revoked proxy. A guard that threw there would
    // replace the failure with a TypeError and let it escape the Durable
    // Object, which is the failure this change exists to stop.
    const container = newContainer();
    const { proxy, revoke } = Proxy.revocable({}, {});
    revoke();
    hooks.containerFetch.mockRejectedValue(proxy);

    const res = await container.fetch(chatRequest());

    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RETRY_AFTER_SECONDS));
    expect(await res.text()).toBe(CONTAINER_UNAVAILABLE_BODY);
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
    // container could not be reached at all. Both layers answer with the same
    // 503, so the log is what tells them apart: only the Durable Object says
    // that the hop rejected with a value that is not an Error.
    const reached = logged.filter((line) => line.includes("could not be reached"));
    expect(reached).toHaveLength(1);
    expect(reached[0]).toContain("the container hop rejected with a value that is not an Error");
    // The failure is logged with a description, so the log says what happened
    // instead of holding a bare date.
    expect(reached[0]).toContain(String(new Date("2026-10-21T11:51:44.000Z")));
    // The hop was tried once: the Durable Object answered instead of
    // throwing, so nothing was replayed.
    expect(hooks.containerFetch).toHaveBeenCalledTimes(1);
  });
});

/**
 * The deployment document is deployment data: it lives in the bound KV
 * namespace under `config-yaml` and is forwarded to the container at boot, so
 * an operator edit applies on the next boot with no redeploy of either half.
 * The `cloudflare:workers` stub's `env` is the object `index.ts` aliases as
 * `workerVars`, so writing a binding into it is the test's Worker binding.
 */
describe("KV config document forwarded to the container", () => {
  const OCC_TENANTS = JSON.stringify({
    "occ.digithings.ai": { slug: "occ", token: "invite-123", gateMode: "invited" },
  });
  const CONFIG_DOC = "version: 1\ndeployment:\n  slug: digithings-ai-config\n";

  afterEach(() => {
    delete stubEnv.DIGICHAT_TENANTS_KV;
  });

  /** One KV namespace answering both keys, or undefined for a given key. */
  function tenantsKv(values: Record<string, string>) {
    return {
      get: async (key: string) => values[key] ?? null,
    };
  }

  it("forwards DIGICHAT_CONFIG_YAML from KV alongside the tenant registry", async () => {
    stubEnv.DIGICHAT_TENANTS_KV = tenantsKv({
      "embed-tenants": OCC_TENANTS,
      "config-yaml": CONFIG_DOC,
    });
    const container = newContainer();
    hooks.containerFetch.mockResolvedValue(new Response("ok"));

    await container.fetch(chatRequest());

    expect(container.envVars.DIGICHAT_CONFIG_YAML).toBe(CONFIG_DOC);
    // OCC must not regress: its KV tenant entry still reaches the container.
    expect(JSON.parse(container.envVars.DIGICHAT_EMBED_TENANTS)).toEqual({
      "occ.digithings.ai": { slug: "occ", token: "invite-123", gateMode: "invited" },
    });
  });

  it("forwards an empty document when the key is absent, leaving file/defaults in charge", async () => {
    stubEnv.DIGICHAT_TENANTS_KV = tenantsKv({ "embed-tenants": OCC_TENANTS });
    const container = newContainer();
    hooks.containerFetch.mockResolvedValue(new Response("ok"));

    await container.fetch(chatRequest());

    expect(container.envVars.DIGICHAT_CONFIG_YAML).toBe("");
  });

  it("keeps serving when the KV read fails", async () => {
    stubEnv.DIGICHAT_TENANTS_KV = {
      get: async () => {
        throw new Error("kv down");
      },
    };
    const container = newContainer();
    hooks.containerFetch.mockResolvedValue(new Response("ok"));

    const res = await container.fetch(chatRequest());

    expect(res.status).toBe(200);
    expect(container.envVars.DIGICHAT_CONFIG_YAML).toBe("");
    expect(container.envVars.DIGICHAT_EMBED_TENANTS).toBe("");
    expect(logged.some((line) => line.includes("config-kv"))).toBe(true);
  });
});

/**
 * The Durable Object outlives the Container: a redeploy of the same commit
 * keeps the same container revision, so the instance (and its boot env) is
 * never rebuilt and a KV edit never reached the container. The tenant registry
 * and the deployment document are therefore re-read once per
 * `BOOT_CONFIG_TTL_MS` window instead of once per boot. A KV read is a cost and
 * a stampede risk, so a burst inside one window must share a single read.
 */
describe("boot config re-read window", () => {
  const DOC_A = "version: 1\ndeployment:\n  slug: a\n";
  const DOC_B = "version: 1\ndeployment:\n  slug: b\n";

  /** One KV namespace answering both keys, counting every read. */
  function countingKv(values: Record<string, string>) {
    const reads: string[] = [];
    return {
      reads,
      values,
      get: async (key: string) => {
        reads.push(key);
        return values[key] ?? null;
      },
    };
  }

  function tenants(token: string): string {
    return JSON.stringify({
      "occ.digithings.ai": { slug: "occ", token, gateMode: "invited" },
    });
  }

  /** The token the container was last handed for the OCC host. */
  function servedToken(container: DigiChatContainer): string | undefined {
    const raw = container.envVars.DIGICHAT_EMBED_TENANTS;
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as Record<string, { token?: string }>;
    return parsed["occ.digithings.ai"]?.token;
  }

  beforeEach(() => {
    hooks.containerFetch.mockResolvedValue(new Response("ok"));
  });

  afterEach(() => {
    delete stubEnv.DIGICHAT_TENANTS_KV;
  });

  it("re-reads KV once the TTL has elapsed and serves the new value", async () => {
    const kv = countingKv({ "embed-tenants": tenants("first"), "config-yaml": DOC_A });
    stubEnv.DIGICHAT_TENANTS_KV = kv;
    const container = newContainer();
    let now = 1_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);

    await container.fetch(chatRequest());
    // One window = one read of each key.
    expect(kv.reads).toEqual(["embed-tenants", "config-yaml"]);
    expect(servedToken(container)).toBe("first");
    expect(container.envVars.DIGICHAT_CONFIG_YAML).toBe(DOC_A);

    // The operator edits KV. Nothing else changes: no deploy, no recycle.
    kv.values["embed-tenants"] = tenants("second");
    kv.values["config-yaml"] = DOC_B;
    now += BOOT_CONFIG_TTL_MS;

    await container.fetch(chatRequest());

    // The count rose, and the value the container now gets is the edited one.
    expect(kv.reads).toEqual(["embed-tenants", "config-yaml", "embed-tenants", "config-yaml"]);
    expect(servedToken(container)).toBe("second");
    expect(container.envVars.DIGICHAT_CONFIG_YAML).toBe(DOC_B);
  });

  it("does not re-read a request that lands inside the window", async () => {
    const kv = countingKv({ "embed-tenants": tenants("first"), "config-yaml": DOC_A });
    stubEnv.DIGICHAT_TENANTS_KV = kv;
    const container = newContainer();
    let now = 2_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);

    await container.fetch(chatRequest());
    // A KV edit inside the window is deliberately not seen: the window bounds
    // the read rate, it does not promise instant propagation.
    kv.values["embed-tenants"] = tenants("second");
    now += BOOT_CONFIG_TTL_MS - 1;
    await container.fetch(chatRequest());

    expect(kv.reads).toHaveLength(2);
    expect(servedToken(container)).toBe("first");
  });

  it("shares one read between two concurrent requests in the same window", async () => {
    const kv = countingKv({ "embed-tenants": tenants("first"), "config-yaml": DOC_A });
    stubEnv.DIGICHAT_TENANTS_KV = kv;
    const container = newContainer();

    await Promise.all([container.fetch(chatRequest()), container.fetch(chatRequest())]);

    // Single-flight: both requests are served, KV is read once per key, so a
    // burst on a cold window cannot stampede the namespace.
    expect(kv.reads).toEqual(["embed-tenants", "config-yaml"]);
    expect(hooks.containerFetch).toHaveBeenCalledTimes(2);
  });

  it("stays fail-soft when KV fails, and retries after the window", async () => {
    const kv = countingKv({ "embed-tenants": tenants("first"), "config-yaml": DOC_A });
    kv.get = async (key: string) => {
      kv.reads.push(key);
      throw new Error("kv down");
    };
    stubEnv.DIGICHAT_TENANTS_KV = kv;
    const container = newContainer();
    let now = 3_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);

    const res = await container.fetch(chatRequest());

    // No 500, no throw: no tenants for this window, container on its own
    // file/defaults for the document.
    expect(res.status).toBe(200);
    expect(container.envVars.DIGICHAT_EMBED_TENANTS).toBe("");
    expect(container.envVars.DIGICHAT_CONFIG_YAML).toBe("");
    expect(logged.some((line) => line.includes("[tenants-kv]"))).toBe(true);
    expect(logged.some((line) => line.includes("[config-kv]"))).toBe(true);

    // A failure does not pin the window: the next window tries again.
    kv.get = async (key: string) => {
      kv.reads.push(key);
      return kv.values[key] ?? null;
    };
    now += BOOT_CONFIG_TTL_MS;
    await container.fetch(chatRequest());

    expect(kv.reads).toHaveLength(4);
    expect(servedToken(container)).toBe("first");
  });

  it("re-arms on onStop so the next request re-reads immediately", async () => {
    const kv = countingKv({ "embed-tenants": tenants("first"), "config-yaml": DOC_A });
    stubEnv.DIGICHAT_TENANTS_KV = kv;
    const container = newContainer();
    const now = 4_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);

    await container.fetch(chatRequest());
    expect(kv.reads).toHaveLength(2);

    container.onStop();
    kv.values["embed-tenants"] = tenants("after-stop");
    // Same instant: only onStop() can make this re-read.
    await container.fetch(chatRequest());

    expect(kv.reads).toHaveLength(4);
    expect(servedToken(container)).toBe("after-stop");
  });
});

describe("the OCC page's API calls through the Worker (DIG-3585)", () => {
  const KEY = "fixture-invite-key";
  /** The cookie the edge sets for KEY: a derived value, never the key. */
  let COOKIE = "";

  beforeEach(async () => {
    COOKIE = await occInviteCookieValue(KEY);
  });

  function envWithInvite(): Env {
    return { ...workerEnv(), OCC_INVITE_KEY: KEY } as Env;
  }

  async function containerSees(init: RequestInit & { path?: string }): Promise<Request> {
    hooks.getContainer.mockReturnValue({ fetch: hooks.containerFetch });
    hooks.containerFetch.mockResolvedValue(new Response("{}", { status: 200 }));
    const { path = "/chat/api/chat", ...rest } = init;
    await worker.fetch(new Request(`https://digithings.ai${path}`, rest), envWithInvite());
    expect(hooks.containerFetch).toHaveBeenCalledTimes(1);
    return hooks.containerFetch.mock.calls[0]![0];
  }

  it("binds a cookie-only call from /chat/occ to the OCC tenant", async () => {
    const seen = await containerSees({
      method: "POST",
      body: "{}",
      headers: { referer: "https://digithings.ai/chat/occ", cookie: `occ_invite=${COOKIE}` },
    });
    expect(seen.headers.get("x-embed-token")).toBe(KEY);
    expect(seen.headers.get("x-embed-host")).toBe("occ.digithings.ai");
    expect(seen.headers.get("cookie")).toBeNull();
  });

  it("binds the tenant-config read the same way", async () => {
    const seen = await containerSees({
      path: "/chat/api/embed/tenant-config",
      headers: { referer: "https://digithings.ai/chat/occ", cookie: `occ_invite=${COOKIE}` },
    });
    expect(seen.headers.get("x-embed-host")).toBe("occ.digithings.ai");
  });

  it("does not bind a house call that carries the cookie", async () => {
    const seen = await containerSees({
      method: "POST",
      body: "{}",
      headers: {
        referer: "https://digithings.ai/chat",
        cookie: `occ_invite=${COOKIE}`,
        "x-digi-tenant": "occ",
      },
    });
    expect(seen.headers.get("x-embed-token")).toBeNull();
    expect(seen.headers.get("x-embed-host")).toBeNull();
    expect(seen.headers.get("x-digi-tenant")).toBeNull();
    expect(seen.headers.get("cookie")).toBeNull();
  });

  it("drops forged tenant headers from the OCC page without the cookie", async () => {
    const seen = await containerSees({
      method: "POST",
      body: "{}",
      headers: {
        referer: "https://digithings.ai/chat/occ",
        "x-embed-token": "guess",
        "x-embed-host": "occ.digithings.ai",
      },
    });
    expect(seen.headers.get("x-embed-token")).toBeNull();
    expect(seen.headers.get("x-embed-host")).toBeNull();
  });

  it("honours OCC_INVITE_MAX_AGE_DAYS: an older cookie is not bound", async () => {
    const twoDaysAgo = Math.floor(Date.now() / 1000) - 2 * 24 * 60 * 60;
    const old = await occInviteCookieValue(KEY, twoDaysAgo);
    const headers = { referer: "https://digithings.ai/chat/occ", cookie: `occ_invite=${old}` };
    hooks.getContainer.mockReturnValue({ fetch: hooks.containerFetch });
    hooks.containerFetch.mockResolvedValue(new Response("{}", { status: 200 }));

    await worker.fetch(
      new Request("https://digithings.ai/chat/api/chat", { method: "POST", body: "{}", headers }),
      { ...envWithInvite(), OCC_INVITE_MAX_AGE_DAYS: "1" } as Env,
    );
    const short = hooks.containerFetch.mock.calls.at(-1)![0];
    expect(short.headers.get("x-embed-token")).toBeNull();
    expect(short.headers.get("x-embed-host")).toBeNull();

    // Same cookie under the default (30 days): still bound.
    await worker.fetch(
      new Request("https://digithings.ai/chat/api/chat", { method: "POST", body: "{}", headers }),
      envWithInvite(),
    );
    const dflt = hooks.containerFetch.mock.calls.at(-1)![0];
    expect(dflt.headers.get("x-embed-host")).toBe("occ.digithings.ai");
  });

  it("answers an invite link with a 302 before anything logs it or the container sees it", async () => {
    // The token may only ever sit in the first request's URL. The Worker
    // must not log that URL, and the container must not receive it: the edge
    // swaps it for the cookie and redirects to the clean address. (The
    // platform's own invocation log is covered by redact_query_string in
    // wrangler.toml, pinned in occ-route.contract.test.ts.)
    const quiet: string[] = [];
    for (const level of ["warn", "info", "debug"] as const) {
      vi.spyOn(console, level).mockImplementation((...args: unknown[]) => {
        quiet.push(args.map((arg) => String(arg)).join(" "));
      });
    }
    hooks.getContainer.mockReturnValue({ fetch: hooks.containerFetch });

    const res = await worker.fetch(
      new Request(`https://digithings.ai/chat/occ?token=${encodeURIComponent(KEY)}`),
      envWithInvite(),
    );

    expect(res.status).toBe(302);
    expect(res.headers.get("location")).not.toContain(KEY);
    expect(res.headers.get("location")).not.toContain("token=");
    // The bare link lands on the canonical page address, trailing slash included.
    expect(res.headers.get("location")).toBe("https://digithings.ai/chat/occ/");
    expect(hooks.containerFetch).not.toHaveBeenCalled();
    expect([...logged, ...quiet]).toEqual([]);
  });

  it("strips a client-sent X-Digi-Tenant on the legacy /api alias too", async () => {
    const seen = await containerSees({
      path: "/api/chat",
      method: "POST",
      body: "{}",
      headers: { "x-digi-tenant": "occ" },
    });
    expect(new URL(seen.url).pathname).toBe("/chat/api/chat");
    expect(seen.headers.get("x-digi-tenant")).toBeNull();
  });
});
