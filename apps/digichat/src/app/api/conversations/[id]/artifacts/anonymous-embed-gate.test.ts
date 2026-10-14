/**
 * Pins the credential set the artifact routes accept, for a tenant configured
 * `auth: anonymous` (DIG-3241).
 *
 * Why this is a pin and not a restatement of the docstrings: the gate under
 * test is the REAL `requireDigiChatAuth`, unmocked. Only the two credential
 * SOURCES are stubbed - the machine-key lookup and the OIDC session - because
 * "this request carries no digichat credential" is the premise, not the
 * finding. What is actually under test is the decision in between: which
 * headers count as a credential at all.
 *
 * Both directions are asserted on the SAME request object, because a 401 on
 * its own is not a finding:
 *
 *   1. **Control.** That request DOES satisfy the embed gate `/api/chat` uses
 *      (`resolveVerifiedEmbedTenant`). Without this arm a 401 would be
 *      indistinguishable from a misconfigured tenant, and this file would
 *      quietly pin a broken token instead of a narrow credential set.
 *   2. **Subject.** That same request does NOT satisfy the artifact gate.
 *
 * The fixture tenant carries a token and the request presents it, so the
 * control never leans on `occ.digithings.ai` staying on the first-party
 * tokenless allowlist. That entry carries a live TODO (DIG-1210) to delete it;
 * a control depending on it would break the day that lands and read as a
 * regression in this file rather than as the migration it is.
 *
 * The third test is what keeps the other two from being satisfied by a gate
 * that simply refuses everything: a valid machine key is still admitted.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth", () => ({
  auth: vi.fn(async () => null),
}));

vi.mock("@/lib/api-key", () => ({
  validateMachineApiKey: vi.fn(async () => null),
}));

vi.mock("@/lib/tenant", () => ({
  tenantSlugForOidcSubject: vi.fn(async () => "acme"),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { resolveVerifiedEmbedTenant } from "@/lib/embed-chat-tenant";
import { validateMachineApiKey } from "@/lib/api-key";
import { resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";

const OCC_HOST = "occ.digithings.ai";
const OCC_TOKEN = "occ-invite-token-fixture";

/**
 * The registry entry. `token` is required by `validateEntry`, and the
 * remaining three fields are the minimum a digigraph tenant validates against.
 */
const OCC_TENANT = {
  slug: "occ",
  backend: { type: "digigraph" },
  gateMode: "ungated",
  token: OCC_TOKEN,
};

/** An `auth: anonymous` embed visitor: valid invite key, no digichat credential. */
function occEmbedRequest(extraHeaders: Record<string, string> = {}): Request {
  return new Request("https://digithings.ai/api/conversations/conv-1/artifacts", {
    headers: {
      "X-Embed-Host": OCC_HOST,
      "X-Embed-Token": OCC_TOKEN,
      Origin: `https://${OCC_HOST}`,
      ...extraHeaders,
    },
  });
}

describe("artifact routes vs an `auth: anonymous` embed tenant", () => {
  beforeEach(() => {
    vi.mocked(validateMachineApiKey).mockResolvedValue(null);
    vi.stubEnv(
      "DIGICHAT_EMBED_TENANTS",
      JSON.stringify({ [OCC_HOST]: OCC_TENANT })
    );
    // The registry is module-cached on first read, so a stubbed env only
    // takes effect after the cache is cleared.
    resetEmbedTenantRegistryForTests();
  });

  it("admits the invite key on the embed gate and refuses it on the artifact gate", async () => {
    const req = occEmbedRequest();

    // Control first: the very same request is a valid OCC caller for the
    // surface `/api/chat` and `/api/embed/tenant-config` actually use.
    const embedTenant = resolveVerifiedEmbedTenant(req);
    expect(embedTenant).not.toBeNull();
    expect(embedTenant?.slug).toBe("occ");

    // Subject: the artifact gate reads only `authorization` and the session
    // cookie, so the same request is refused here.
    const auth = await requireDigiChatAuth(req);
    expect(auth).toBeInstanceOf(Response);
    expect((auth as Response).status).toBe(401);
  });

  it("still refuses a request that carries no embed credential at all", async () => {
    // Without this, the test above could be satisfied by any 401 - including
    // one produced by an unrelated failure such as a misconfigured registry.
    const bare = new Request("https://digithings.ai/api/conversations/conv-1/artifacts");

    expect(resolveVerifiedEmbedTenant(bare)).toBeNull();

    const auth = await requireDigiChatAuth(bare);
    expect(auth).toBeInstanceOf(Response);
    expect((auth as Response).status).toBe(401);
  });

  it("still admits a machine key, so the gate discriminates rather than refusing all", async () => {
    // The non-vacuity arm for the whole file: a gate that refused every
    // caller would make both tests above pass.
    vi.mocked(validateMachineApiKey).mockResolvedValue({
      tenantSlug: "acme",
    } as never);

    const auth = await requireDigiChatAuth(occEmbedRequest());
    expect(auth).not.toBeInstanceOf(Response);
    expect(auth).toMatchObject({ tenantSlug: "acme" });
  });
});
