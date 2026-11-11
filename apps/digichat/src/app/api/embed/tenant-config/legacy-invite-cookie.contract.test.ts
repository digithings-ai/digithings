/**
 * DIG-3585 contract: the legacy invite page's tenant-config read reaches the
 * invited tenant only through the edge-bound invite cookie.
 *
 * After the invite link's 302 the browser on the legacy invite page holds the
 * invite only as the `LEGACY_INVITE_COOKIE` cookie; its URL carries no ?token=
 * and no ?host=. The digichat Worker's `bindLegacyInviteApiCall` is what turns a
 * /chat/api/* call from that page into an invited-tenant call, and only when
 * the cookie is valid AND the Referer is the legacy invite page. These tests run
 * the real Worker binding and the real app route back to back, the way
 * production chains them. The page path, cookie name and embed host come from
 * the gate module and the tenant slug from the app's invite-only map; the
 * tenant's contents are a neutral fixture.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";
import {
  bindLegacyInviteApiCall,
  legacyInviteCookieValue,
  LEGACY_INVITE_COOKIE,
  LEGACY_INVITE_EMBED_HOST,
  LEGACY_INVITE_PAGE_PATH,
} from "../../../../../../digichat-cloudflare/src/legacy-invite-gate";
import { INVITE_ONLY_EMBED_HOSTS } from "@/lib/embed-invite-only";
import { resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";
import { resetDigichatConfigForTests } from "@/lib/deploy-config/loader";

/** A test fixture, not a credential. */
const INVITE = "example-invite-fixture-not-a-secret";
const INVITE_PAGE = `https://digithings.ai${LEGACY_INVITE_PAGE_PATH}`;
/**
 * The tenant the app pins to the invite host. It is read from the app's own
 * invite-only map, because the route refuses any other slug on that host; the
 * rest of the tenant below is a neutral fixture.
 */
const INVITED_SLUG = INVITE_ONLY_EMBED_HOSTS.get(LEGACY_INVITE_EMBED_HOST) ?? "";

const REGISTRY = JSON.stringify({
  [LEGACY_INVITE_EMBED_HOST]: {
    slug: INVITED_SLUG,
    gateMode: "ungated",
    skin: "digichat",
    attribution: true,
    token: INVITE,
    backend: {
      type: "digigraph",
      digisearchIndex: "tenant_help,tenant-tickets",
      vaultPathPrefix: "clients/example-client-fixture",
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
  await bindLegacyInviteApiCall(req, INVITE);
  const res = await GET(req);
  expect(res.status).toBe(200);
  return (await res.json()) as { slug?: string; mcp?: { servers?: unknown[] } };
}

function expectNotInvited(body: { slug?: string; mcp?: { servers?: unknown[] } }): void {
  expect(body.slug).not.toBe(INVITED_SLUG);
  expect(JSON.stringify(body)).not.toMatch(/tenant_help|tenant-tickets|tickets-mcp|example-client-fixture/);
}

/** The cookie the edge set when the invite link was opened. */
let COOKIE = "";

beforeEach(async () => {
  // Guards the fixture: an empty slug would make the negative cases vacuous.
  expect(INVITED_SLUG).toMatch(/^[a-z0-9-]+$/);
  COOKIE = await legacyInviteCookieValue(INVITE);
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

describe("tenant-config from the legacy invite page (DIG-3585)", () => {
  it("resolves a cookie-only read from the invite page to the invited tenant", async () => {
    const body = await tenantSeen(
      browserRead(INVITE_PAGE, { cookie: `${LEGACY_INVITE_COOKIE}=${COOKIE}` }),
    );
    expect(body.slug).toBe(INVITED_SLUG);
    // The invited tenant's tools come with it (the negative cases below must never see them).
    expect(JSON.stringify(body.mcp)).toContain("tickets-mcp");
    // The client-safe projection: the tool is listed, its secret never is.
    expect(JSON.stringify(body)).not.toContain(INVITE);
  });

  it("never resolves the invited tenant from the invite page without the cookie", async () => {
    expectNotInvited(await tenantSeen(browserRead(INVITE_PAGE)));
  });

  it("never resolves the invited tenant from the invite page with a wrong cookie and forged headers", async () => {
    expectNotInvited(
      await tenantSeen(
        browserRead(INVITE_PAGE, {
          cookie: `${LEGACY_INVITE_COOKIE}=guess`,
          "x-embed-token": "guess",
          "x-embed-host": `https://${LEGACY_INVITE_EMBED_HOST}`,
        }),
      ),
    );
  });

  it("never upgrades a house read that carries the cookie", async () => {
    expectNotInvited(
      await tenantSeen(
        browserRead("https://digithings.ai/chat", { cookie: `${LEGACY_INVITE_COOKIE}=${COOKIE}` }),
      ),
    );
  });
});
