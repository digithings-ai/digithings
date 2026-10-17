import { beforeEach, describe, expect, it, vi } from "vitest";
import { auth } from "@/auth";
import { validateMachineApiKey } from "@/lib/api-key";
import { tenantSlugForOidcSubject } from "@/lib/tenant";
import { requireDigiChatAuth } from "./request-auth";

vi.mock("@/auth", () => ({ auth: vi.fn() }));
vi.mock("@/lib/api-key", () => ({ validateMachineApiKey: vi.fn() }));
vi.mock("@/lib/tenant", () => ({ tenantSlugForOidcSubject: vi.fn() }));

const deskSession = {
  user: { id: "user-1", app_metadata: { plan_tier: "desk" } },
  expires: "2099-01-01T00:00:00.000Z",
};

describe("requireDigiChatAuth plan tier", () => {
  beforeEach(() => {
    vi.mocked(auth).mockReset();
    vi.mocked(validateMachineApiKey).mockReset();
    vi.mocked(tenantSlugForOidcSubject).mockReset();
  });

  it("does not inherit a cookie session plan tier on a machine-key request", async () => {
    vi.mocked(validateMachineApiKey).mockResolvedValue({ tenantSlug: "acme" });
    vi.mocked(auth).mockResolvedValue(deskSession as never);

    const result = await requireDigiChatAuth(
      new Request("http://localhost/api/chat", {
        headers: { authorization: "Bearer digi_live_test" },
      }),
    );

    expect(result).toMatchObject({
      tenantSlug: "acme",
      ownerUserSub: "machine:acme",
    });
    expect((result as { plan_tier?: string }).plan_tier).toBeUndefined();
    expect(tenantSlugForOidcSubject).not.toHaveBeenCalled();
  });

  it("keeps the session plan tier when the caller is the signed-in user", async () => {
    vi.mocked(validateMachineApiKey).mockResolvedValue(null);
    vi.mocked(auth).mockResolvedValue(deskSession as never);
    vi.mocked(tenantSlugForOidcSubject).mockResolvedValue("home");

    const result = await requireDigiChatAuth(new Request("http://localhost/api/chat"));

    expect(result).toMatchObject({
      tenantSlug: "home",
      ownerUserSub: "user-1",
      plan_tier: "desk",
    });
  });
});
