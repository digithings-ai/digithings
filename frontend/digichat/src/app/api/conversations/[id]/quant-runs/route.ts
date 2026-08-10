import { requireDigiChatAuth } from "@/lib/request-auth";
import {
  insertQuantRun,
  listQuantRuns,
  tenantIdBySlug,
} from "@/lib/conversations-repo";
import { getDb } from "@/db";

type RouteContext = { params: Promise<{ id: string }> };

export async function GET(req: Request, ctx: RouteContext) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;

  const { id: conversationId } = await ctx.params;
  const db = getDb();
  if (!db) {
    return Response.json({ error: "database_unavailable" }, { status: 503 });
  }

  const tenantId = await tenantIdBySlug(db, authCtx.tenantSlug);
  if (!tenantId) {
    return Response.json({ error: "tenant_not_found" }, { status: 404 });
  }

  const runs = await listQuantRuns(db, {
    conversationId,
    tenantId,
    ownerUserSub: authCtx.ownerUserSub,
  });

  return Response.json({ runs });
}

export async function POST(req: Request, ctx: RouteContext) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;

  const { id: conversationId } = await ctx.params;
  let body: {
    label?: string;
    strategyName: string;
    symbols: string[];
    strategyParams?: Record<string, unknown> | null;
    backtestResult: Record<string, unknown>;
  };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }

  if (
    !body.strategyName ||
    !Array.isArray(body.symbols) ||
    !body.backtestResult ||
    typeof body.backtestResult !== "object"
  ) {
    return Response.json({ error: "invalid_body" }, { status: 400 });
  }

  const db = getDb();
  if (!db) {
    return Response.json({ error: "database_unavailable" }, { status: 503 });
  }

  const tenantId = await tenantIdBySlug(db, authCtx.tenantSlug);
  if (!tenantId) {
    return Response.json({ error: "tenant_not_found" }, { status: 404 });
  }

  const id = await insertQuantRun(db, {
    conversationId,
    tenantId,
    ownerUserSub: authCtx.ownerUserSub,
    label: body.label,
    strategyName: body.strategyName,
    symbols: body.symbols,
    strategyParams: body.strategyParams,
    backtestResult: body.backtestResult,
  });

  if (!id) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }

  return Response.json({ id }, { status: 201 });
}
