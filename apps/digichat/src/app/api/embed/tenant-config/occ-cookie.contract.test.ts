/**
 * DIG-3585 contract: the OCC page's tenant-config read is OCC only through the
 * edge-bound invite cookie.
 *
 * After the invite link's 302 the browser on /chat/occ holds the invite only
 * as the `occ_invite` cookie; its URL carries no ?token= and no ?host=. The
 * digichat Worker's `bindOccApiCall` is what turns a /chat/api/* call from
 * that page into an OCC call — and only when the cookie is valid AND the
 * Referer is the OCC page. These tests run the real Worker binding and the
 * real app route back to back, the way production chains them.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";
import { bindOccApiCall } from "../../../../../../digichat-cloudflare/src/occ-gate";
import { resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";
import { resetDigichatConfigForTests } from "@/lib/deploy-config/loader";

/** A test fixture, not a credential. */
const INVITE = "occ-invite-fixture-not-a-secret";
const OCC_PAGE = "https://digithings.ai/chat/occ";

const REGISTRY = JSON.stringify({
  "occ.digithings.ai": {
    slug: "occ",
    gateMode: "ungated",
    skin: "digichat",
    attribution: true,
    token: INVITE,
    backend: {
      type: "digigraph",
      digisearchIndex: "tenant_help,tenant-tickets",
      vaultPathPrefix: "clients/occ-fixture",
    },
    mcp: {
      servers: [
        {
          id: "tickets-mcp",
          url: "http://tickets-mcp:8770/mcp",
          label: "Tickets",
          default: true,
          allowedTools: ["search_tickets"],
          mutatingTools: [],
        },
      ],
      allowUserServers: false,
      allowAddForm: false,
    },
  },
});

/** What the browser on a page sends, before the edge touches it. */
function browserRead(referer: string, headers: Record<string, string> = {}): Request {
  return new Request("https://digithings.ai/chat/api/embed/tenant-config", {
    headers: {
      referer,
      origin: "https://digithings.ai",
      // The client's own guess at its host when the URL names none.
      "x-embed-host": "https://digithings.ai",
      ...headers,
    },
  });
}

async function tenantSeen(req: Request): Promise<{ slug?: string; mcp?: { servers?: unknown[] } }> {
  bindOccApiCall(req, INVITE);
  const res = await GET(req);
  expect(res.status).toBe(200);
  return (await res.json()) as { slug?: string; mcp?: { servers?: unknown[] } };
}

function expectNotOcc(body: { slug?: string; mcp?: { servers?: unknown[] } }): void {
  expect(body.slug).not.toBe("occ");
  expect(JSON.stringify(body)).not.toMatch(/tenant_help|tenant-tickets|tickets-mcp|occ-fixture/);
}

beforeEach(() => {
  vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
  vi.stubEnv("DIGICHAT_CONFIG_PATH", "");
  resetEmbedTenantRegistryForTests();
  resetDigichatConfigForTests();
});

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
  resetDigichatConfigForTests();
});

describe("tenant-config from the OCC page (DIG-3585)", () => {
  it("resolves a cookie-only read from /chat/occ to the OCC tenant", async () => {
    const body = await tenantSeen(browserRead(OCC_PAGE, { cookie: `occ_invite=${INVITE}` }));
    expect(body.slug).toBe("occ");
    // The OCC tools come with it (the negative cases below must never see them).
    expect(JSON.stringify(body.mcp)).toContain("tickets-mcp");
    // The client-safe projection: the tool is listed, its secret never is.
    expect(JSON.stringify(body)).not.toContain(INVITE);
  });

  it("never resolves OCC from /chat/occ without the cookie", async () => {
    expectNotOcc(await tenantSeen(browserRead(OCC_PAGE)));
  });

  it("never resolves OCC from /chat/occ with a wrong cookie and forged headers", async () => {
    expectNotOcc(
      await tenantSeen(
        browserRead(OCC_PAGE, {
          cookie: "occ_invite=guess",
          "x-embed-token": "guess",
          "x-embed-host": "https://occ.digithings.ai",
        }),
      ),
    );
  });

  it("never upgrades a house read that carries the cookie", async () => {
    expectNotOcc(
      await tenantSeen(
        browserRead("https://digithings.ai/chat", { cookie: `occ_invite=${INVITE}` }),
      ),
    );
  });
});
