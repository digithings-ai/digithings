import { getDb } from "@/db";
import { getDigichatConfig } from "@/lib/deploy-config/loader";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";
import { getConversationMessages, tenantIdBySlug } from "@/lib/conversations-repo";
import { replayChromeForDeployment, replayExportedAt } from "@/lib/replay-export";
import { requireDigiChatAuth } from "@/lib/request-auth";
import { loadReplayStyles } from "@digithings/ui/replay/assets";
import { buildReplayHtml, messagesToReplay, replayDownloadName } from "@digithings/ui/replay";

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

  const data = await getConversationMessages(db, conversationId, tenantId, authCtx.ownerUserSub);
  if (!data) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }

  const url = new URL(req.url);
  const doc = messagesToReplay(
    data.messages,
    replayChromeForDeployment(readDeployment(authCtx.tenantSlug), authCtx.tenantSlug, url),
    replayExportedAt(url),
  );
  let css: string;
  try {
    css = loadReplayStyles();
  } catch {
    return Response.json({ error: "replay_assets_unavailable" }, { status: 503 });
  }
  const html = buildReplayHtml(doc, css);
  const filename = replayDownloadName(doc);
  return new Response(html, {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "content-disposition": `attachment; filename="${filename}"`,
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

/**
 * The caller's own deployment, by tenant slug. A single-install config has one
 * deployment and uses it. With several hosts and no slug match the file gets
 * neutral branding rather than another tenant's.
 */
function readDeployment(tenantSlug: string): DigichatDeployment | null {
  try {
    const cfg = getDigichatConfig();
    const all = [cfg.deployment, ...Object.values(cfg.hosts ?? {})].filter(
      (dep): dep is DigichatDeployment => Boolean(dep),
    );
    return all.find((dep) => dep.slug === tenantSlug) ?? (all.length === 1 ? all[0]! : null);
  } catch {
    return null;
  }
}
