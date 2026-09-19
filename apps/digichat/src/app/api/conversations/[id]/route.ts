import type { UIMessage } from "ai";
import { getDb } from "@/db";
import { requireDigiChatAuth } from "@/lib/request-auth";
import {
  deleteConversation,
  getConversationMessages,
  replaceConversationMessages,
  tenantIdBySlug,
} from "@/lib/conversations-repo";

type RouteContext = { params: Promise<{ id: string }> };

export async function GET(req: Request, ctx: RouteContext) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;

  const { id: conversationId } = await ctx.params;
  const db = getDb();
  if (!db) {
    return Response.json(
      { error: "database_unavailable" },
      { status: 503, headers: { "content-type": "application/json" } }
    );
  }

  const tenantId = await tenantIdBySlug(db, authCtx.tenantSlug);
  if (!tenantId) {
    return Response.json({ error: "tenant_not_found" }, { status: 404 });
  }

  const data = await getConversationMessages(
    db,
    conversationId,
    tenantId,
    authCtx.ownerUserSub
  );

  if (!data) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }

  return Response.json({
    id: conversationId,
    title: data.title,
    messages: data.messages,
  });
}

export async function PUT(req: Request, ctx: RouteContext) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;

  const { id: conversationId } = await ctx.params;

  let body: { title?: string; messages?: UIMessage[]; allowTruncate?: boolean };
  try {
    body = (await req.json()) as {
      title?: string;
      messages?: UIMessage[];
      allowTruncate?: boolean;
    };
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }

  const messages = body.messages;
  if (!Array.isArray(messages)) {
    return Response.json({ error: "messages_required" }, { status: 400 });
  }

  const db = getDb();
  if (!db) {
    return Response.json({ error: "database_unavailable" }, { status: 503 });
  }

  const tenantId = await tenantIdBySlug(db, authCtx.tenantSlug);
  if (!tenantId) {
    return Response.json({ error: "tenant_not_found" }, { status: 400 });
  }

  const result = await replaceConversationMessages(db, {
    conversationId,
    tenantId,
    ownerUserSub: authCtx.ownerUserSub,
    title: typeof body.title === "string" ? body.title : undefined,
    messages,
    allowTruncate: body.allowTruncate === true,
  });

  if (result === "not_found") {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  if (result === "would_truncate") {
    return Response.json(
      {
        error: "would_truncate",
        detail:
          "PUT would drop existing messages; re-fetch the conversation or pass allowTruncate",
      },
      { status: 409 }
    );
  }

  return new Response(null, { status: 204 });
}

export async function DELETE(req: Request, ctx: RouteContext) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;

  const { id: conversationId } = await ctx.params;
  const db = getDb();
  if (!db) {
    return Response.json({ error: "database_unavailable" }, { status: 503 });
  }

  const tenantId = await tenantIdBySlug(db, authCtx.tenantSlug);
  if (!tenantId) {
    return Response.json({ error: "tenant_not_found" }, { status: 400 });
  }

  const ok = await deleteConversation(db, {
    conversationId,
    tenantId,
    ownerUserSub: authCtx.ownerUserSub,
  });

  if (!ok) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }

  return new Response(null, { status: 204 });
}
