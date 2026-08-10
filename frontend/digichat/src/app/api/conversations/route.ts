import { getDb } from "@/db";
import { requireDigiChatAuth } from "@/lib/request-auth";
import {
  createConversation,
  listConversationSummaries,
  tenantIdBySlug,
} from "@/lib/conversations-repo";

export async function GET(req: Request) {
  const ctx = await requireDigiChatAuth(req);
  if (ctx instanceof Response) return ctx;

  const db = getDb();
  if (!db) {
    return Response.json({ serverPersistence: false, conversations: [] });
  }

  const tenantId = await tenantIdBySlug(db, ctx.tenantSlug);
  if (!tenantId) {
    return Response.json({ serverPersistence: true, conversations: [] });
  }

  const rows = await listConversationSummaries(
    db,
    tenantId,
    ctx.ownerUserSub
  );

  return Response.json({
    serverPersistence: true,
    conversations: rows.map((c) => ({
      id: c.id,
      title: c.title,
      updatedAt: c.updatedAt.toISOString(),
    })),
  });
}

export async function POST(req: Request) {
  const ctx = await requireDigiChatAuth(req);
  if (ctx instanceof Response) return ctx;

  const db = getDb();
  if (!db) {
    return Response.json(
      { error: "database_unavailable" },
      { status: 503, headers: { "content-type": "application/json" } }
    );
  }

  const tenantId = await tenantIdBySlug(db, ctx.tenantSlug);
  if (!tenantId) {
    return Response.json(
      { error: "tenant_not_found" },
      { status: 400, headers: { "content-type": "application/json" } }
    );
  }

  let body: { id?: string; title?: string };
  try {
    body = (await req.json()) as { id?: string; title?: string };
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }

  const id = await createConversation(db, {
    tenantId,
    ownerUserSub: ctx.ownerUserSub,
    id: typeof body.id === "string" ? body.id : undefined,
    title: typeof body.title === "string" ? body.title : undefined,
  });

  return Response.json({ id }, { status: 201 });
}
