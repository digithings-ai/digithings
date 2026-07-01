import { auth } from "@/auth";
import { validateMachineApiKey } from "@/lib/api-key";
import { tenantSlugForOidcSubject } from "@/lib/tenant";

export type DigiChatAuthContext = {
  tenantSlug: string;
  /** OIDC subject or `machine:${tenantSlug}` for API keys. */
  ownerUserSub: string;
};

export async function requireDigiChatAuth(
  req: Request
): Promise<DigiChatAuthContext | Response> {
  const machine = await validateMachineApiKey(req.headers.get("authorization"));
  const session = await auth();

  if (!machine && !session?.user) {
    return new Response(
      JSON.stringify({
        error: "unauthorized",
        message:
          "Sign in or send Authorization: Bearer digi_live_… (DigiChat machine key). DigiKey dgk_live_… keys are exchanged after auth — see ARCHITECTURE.md §Machine API key prefixes.",
      }),
      { status: 401, headers: { "content-type": "application/json" } }
    );
  }

  let tenantSlug: string;
  try {
    tenantSlug = machine
      ? machine.tenantSlug
      : await tenantSlugForOidcSubject(session!.user!.id);
  } catch (e) {
    const message = e instanceof Error ? e.message : "tenant_resolution_failed";
    return new Response(JSON.stringify({ error: "tenant_error", message }), {
      status: 503,
      headers: { "content-type": "application/json" },
    });
  }
  const ownerUserSub = machine
    ? `machine:${tenantSlug}`
    : session!.user!.id;

  return { tenantSlug, ownerUserSub };
}
