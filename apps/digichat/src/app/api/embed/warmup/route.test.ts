import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";
import {
  resetDigichatConfigForTests,
  setDigichatConfigForTests,
} from "@/lib/deploy-config/loader";

vi.mock("@/lib/ecosystem", () => ({
  getEcosystemEndpoints: async () => ({
    digigraphUrl: "http://digigraph.invalid",
  }),
}));

/** A digigraph install that is not answering: every probe fails. */
function failingFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("nope", { status: 503 })),
  );
}

function configWithBackend(type: "foundry" | "digigraph") {
  setDigichatConfigForTests({
    version: 1,
    deployment: {
      slug: "trial",
      chrome: { mode: "embed" },
      backend:
        type === "foundry"
          ? {
              type: "foundry",
              projectEndpoint: "https://example.services.ai.azure.com/api/projects/p",
              agentName: "agent",
            }
          : { type: "digigraph" },
    },
  } as never);
}

describe("GET /api/embed/warmup", () => {
  afterEach(() => {
    resetDigichatConfigForTests();
    vi.unstubAllGlobals();
    delete process.env.DIGICHAT_ENABLED_SERVICES;
  });

  it("does not wait on digigraph for a foundry install", async () => {
    failingFetch();
    configWithBackend("foundry");

    const res = await GET();
    const body = (await res.json()) as { ready: boolean; services: Record<string, string> };

    // The default enabled-service set names digigraph, but a foundry install
    // has no digigraph to wake. Probing it parked the UI on a boot screen.
    expect(body.services.assistant).toBeUndefined();
    expect(body.ready).toBe(true);
  });

  it("still reports digigraph as waking for a digigraph install", async () => {
    failingFetch();
    configWithBackend("digigraph");

    const res = await GET();
    const body = (await res.json()) as { ready: boolean; services: Record<string, string> };

    expect(body.services.assistant).toBe("waking");
    expect(body.ready).toBe(false);
  });
});
