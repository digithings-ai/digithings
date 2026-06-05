import type { DigiChatAuthContext } from "@/lib/request-auth";

export type ChatTenantContext = {
  tenantSlug: string;
  ownerUserSub: string;
};

/** Resolve tenant + owner for authenticated POST /api/chat (SIMP-027). */
export async function resolveChatTenantContext(
  _req: Request,
  authResult: DigiChatAuthContext | Response
): Promise<ChatTenantContext | Response> {
  if (authResult instanceof Response) {
    return authResult;
  }

  return {
    tenantSlug: authResult.tenantSlug,
    ownerUserSub: authResult.ownerUserSub,
  };
}
