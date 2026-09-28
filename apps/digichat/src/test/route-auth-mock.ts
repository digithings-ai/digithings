import type { DigiChatAuthContext } from "@/lib/request-auth";

export const mockAuthCtx: DigiChatAuthContext = {
  tenantSlug: "acme",
  ownerUserSub: "user-1",
};

export const unauthorizedResponse = new Response(
  JSON.stringify({ error: "unauthorized" }),
  { status: 401, headers: { "content-type": "application/json" } }
);
