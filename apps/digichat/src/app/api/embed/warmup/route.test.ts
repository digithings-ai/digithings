import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";

const loader = vi.hoisted(() => ({ getDigichatConfig: vi.fn() }));
vi.mock("@/lib/deploy-config/loader", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/deploy-config/loader")>();
  return { ...actual, getDigichatConfig: loader.getDigichatConfig };
});

vi.mock("@/lib/ecosystem", () => ({
  getEcosystemEndpoints: async () => ({
    digigraphUrl: "http://digigraph.invalid",
  }),
}));

/** A digigraph install that is not answering: every probe fails. */
function failingFetch() {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 503 })));
}

function config(overrides: Record<string, unknown>) {
  loader.getDigichatConfig.mockReturnValue({ version: 1, ...overrides });
}

async function warmup() {
  const res = await GET();
  return (await res.json()) as { ready: boolean; services: Record<string, string> };
}

describe("GET /api/embed/warmup", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    delete process.env.DIGICHAT_ENABLED_SERVICES;
  });

  it("does not wait on digigraph for a foundry install", async () => {
    failingFetch();
    config({
      deployment: {
        slug: "trial",
        backend: {
          type: "foundry",
          projectEndpoint: "https://example.services.ai.azure.com/api/projects/p",
          agentName: "agent",
        },
      },
    });

    const body = await warmup();
    // The default enabled-service set names digigraph, but a foundry install
    // has no digigraph to wake. Probing it parked the UI on a boot screen.
    expect(body.services.assistant).toBeUndefined();
    expect(body.ready).toBe(true);
  });

  it("does not wait on digigraph for a registry of foundry tenants", async () => {
    failingFetch();
    config({
      hosts: {
        "tenant.example": {
          slug: "tenant",
          backend: {
            type: "foundry",
            projectEndpoint: "https://example.services.ai.azure.com/api/projects/p",
            agentName: "agent",
          },
        },
      },
    });

    const body = await warmup();
    expect(body.services.assistant).toBeUndefined();
    expect(body.ready).toBe(true);
  });

  it("still reports digigraph as waking for a digigraph install", async () => {
    failingFetch();
    config({ deployment: { slug: "trial", backend: { type: "digigraph" } } });

    const body = await warmup();
    expect(body.services.assistant).toBe("waking");
    expect(body.ready).toBe(false);
  });

  it("still probes digigraph when one tenant of a mixed install needs it", async () => {
    failingFetch();
    config({
      deployment: {
        slug: "trial",
        backend: {
          type: "foundry",
          projectEndpoint: "https://example.services.ai.azure.com/api/projects/p",
          agentName: "agent",
        },
      },
      hosts: {
        "graph.example": { slug: "graph", backend: { type: "digigraph" } },
      },
    });

    const body = await warmup();
    // A false "ready" is worse than a false "waking": this install does need
    // digigraph for one of its tenants.
    expect(body.services.assistant).toBe("waking");
    expect(body.ready).toBe(false);
  });

  it("probes digigraph when the config cannot be read", async () => {
    failingFetch();
    loader.getDigichatConfig.mockImplementation(() => {
      throw new Error("config unreadable");
    });

    const body = await warmup();
    expect(body.services.assistant).toBe("waking");
  });
});
