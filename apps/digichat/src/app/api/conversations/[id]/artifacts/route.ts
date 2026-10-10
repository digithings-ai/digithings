/**
 * `/api/conversations/[id]/artifacts` - session-scoped artifact metadata.
 *
 * The route holds no artifact policy of its own. Authentication is
 * `requireDigiChatAuth` (the same gate every DigiChat route uses, so an
 * OCC embed's invite key is honoured here too), ownership is the guard inside
 * `artifacts-repo.ts`, and the link lifetime is `session-links.ts`.
 *
 * `getDb()` returning null is a real state, not an error to hide: the
 * Cloudflare deployment is DB-less (audit D5, issue #4314) and answers
 * `database_unavailable` exactly as the quant-runs route does.
 */
import { getDb } from "@/db";
import { deleteArtifact, getArtifactByToken, insertArtifact, listArtifacts } from "@/lib/artifacts-repo";
import {
  createFileBlobStore,
  createR2BlobStore,
  defaultFileBlobRoot,
  type ArtifactBlobStore,
  type R2Like,
} from "@/lib/artifact-blobs";
import { requireDigiChatAuth } from "@/lib/request-auth";
import { tenantIdBySlug } from "@/lib/conversations-repo";

type RouteContext = { params: Promise<{ id: string }> };

/** Max artifact bytes accepted in one write: 25 MiB. */
const MAX_ARTIFACT_BYTES = 25 * 1024 * 1024;
const DEFAULT_KIND = "file";

/**
 * Blob backend. R2 when a bucket is supplied (hosted / Miniflare), filesystem
 * otherwise. The bucket is passed in rather than read off `process.env` so
 * the choice is explicit at the call site and testable without a Worker.
 */
function blobStore(env: { DIGICHAT_ARTIFACTS?: R2Like }): ArtifactBlobStore {
  const bucket = env.DIGICHAT_ARTIFACTS;
  if (bucket && typeof bucket.put === "function") return createR2BlobStore(bucket);
  return createFileBlobStore(defaultFileBlobRoot());
}

/** Content types the browser can render inline; everything else downloads. */
const INLINE_PREFIXES = ["text/", "application/json", "image/png", "image/jpeg", "image/gif", "image/webp"];
function isViewable(mediaType: string): boolean {
  return INLINE_PREFIXES.some((prefix) => mediaType.startsWith(prefix));
}

function kindFor(mediaType: string, name: string): string {
  const lower = name.toLowerCase();
  if (mediaType === "text/csv" || lower.endsWith(".csv") || lower.endsWith(".json")) return "table";
  if (isViewable(mediaType)) return mediaType.startsWith("image/") ? "image" : "text";
  return DEFAULT_KIND;
}

export async function GET(req: Request, ctx: RouteContext) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;
  const { id: conversationId } = await ctx.params;
  const db = getDb();
  if (!db) return Response.json({ error: "database_unavailable" }, { status: 503 });
  const tenantId = await tenantIdBySlug(db, authCtx.tenantSlug);
  if (!tenantId) return Response.json({ error: "tenant_not_found" }, { status: 404 });
  const artifacts = await listArtifacts(db, {
    conversationId,
    tenantId,
    ownerUserSub: authCtx.ownerUserSub,
  });
  return Response.json({
    artifacts: artifacts.map((artifact) => ({
      ...artifact,
      viewable: isViewable(artifact.mediaType),
    })),
  });
}

export async function POST(req: Request, ctx: RouteContext) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;
  const { id: conversationId } = await ctx.params;
  const db = getDb();
  if (!db) return Response.json({ error: "database_unavailable" }, { status: 503 });
  const tenantId = await tenantIdBySlug(db, authCtx.tenantSlug);
  if (!tenantId) return Response.json({ error: "tenant_not_found" }, { status: 404 });

  let body: { token?: unknown; name?: unknown; mediaType?: unknown; bytes?: unknown; summary?: unknown };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }
  if (typeof body.token !== "string" || !body.token.trim()) {
    return Response.json({ error: "invalid_body" }, { status: 400 });
  }
  if (typeof body.name !== "string" || !body.name.trim()) {
    return Response.json({ error: "invalid_body" }, { status: 400 });
  }
  if (typeof body.mediaType !== "string" || !body.mediaType.trim()) {
    return Response.json({ error: "invalid_body" }, { status: 400 });
  }
  if (!Array.isArray(body.bytes) && !(body.bytes instanceof Uint8Array)) {
    return Response.json({ error: "invalid_body" }, { status: 400 });
  }
  const bytes = new Uint8Array(body.bytes as number[] | Uint8Array);
  if (bytes.byteLength === 0 || bytes.byteLength > MAX_ARTIFACT_BYTES) {
    return Response.json({ error: "invalid_body" }, { status: 400 });
  }

  const token = body.token.trim();
  const storageKey = `artifacts/${conversationId}/${token}`;
  const mediaType = body.mediaType.trim();
  try {
    await blobStore(process.env as { DIGICHAT_ARTIFACTS?: R2Like }).put(storageKey, bytes, mediaType);
  } catch (error) {
    return Response.json(
      { error: "artifact_write_failed", detail: (error as Error).message },
      { status: 500 }
    );
  }
  const id = await insertArtifact(db, {
    conversationId,
    tenantId,
    ownerUserSub: authCtx.ownerUserSub,
    token,
    name: body.name.trim(),
    mediaType,
    byteSize: bytes.byteLength,
    storageKey,
    kind: kindFor(mediaType, body.name),
    summary: typeof body.summary === "string" && body.summary.trim() ? body.summary.trim() : null,
  });
  if (!id) {
    // Ownership failed: drop the bytes we just wrote rather than leave an
    // orphan blob no row points at.
    await blobStore(process.env as { DIGICHAT_ARTIFACTS?: R2Like }).delete(storageKey).catch(() => {});
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  return Response.json({ id, storageKey }, { status: 201 });
}

export async function DELETE(req: Request, ctx: RouteContext) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;
  const { id: conversationId } = await ctx.params;
  const db = getDb();
  if (!db) return Response.json({ error: "database_unavailable" }, { status: 503 });
  const tenantId = await tenantIdBySlug(db, authCtx.tenantSlug);
  if (!tenantId) return Response.json({ error: "tenant_not_found" }, { status: 404 });
  const token = new URL(req.url).searchParams.get("token")?.trim();
  if (!token) return Response.json({ error: "invalid_body" }, { status: 400 });
  const storageKey = await deleteArtifact(db, {
    conversationId,
    tenantId,
    ownerUserSub: authCtx.ownerUserSub,
    token,
  });
  if (!storageKey) return Response.json({ error: "not_found" }, { status: 404 });
  await blobStore(process.env as { DIGICHAT_ARTIFACTS?: R2Like })
    .delete(storageKey)
    .catch(() => {});
  return Response.json({ deleted: true });
}

/**
 * `/api/conversations/[id]/artifacts/blob` behaviour, exposed for the link
 * the model embeds and `/artifacts` opens. Kept here rather than a second
 * file so the ownership and expiry checks cannot drift apart.
 */
export async function serveArtifact(req: Request, ctx: RouteContext & { token?: string }) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;
  const { id: conversationId } = await ctx.params;
  const db = getDb();
  if (!db) return Response.json({ error: "database_unavailable" }, { status: 503 });
  const tenantId = await tenantIdBySlug(db, authCtx.tenantSlug);
  if (!tenantId) return Response.json({ error: "tenant_not_found" }, { status: 404 });
  const token = ctx.token ?? new URL(req.url).searchParams.get("token")?.trim();
  if (!token) return Response.json({ error: "invalid_body" }, { status: 400 });
  const artifact = await getArtifactByToken(db, {
    conversationId,
    tenantId,
    ownerUserSub: authCtx.ownerUserSub,
    token,
  });
  if (!artifact) return Response.json({ error: "not_found" }, { status: 404 });
  const store = blobStore(process.env as { DIGICHAT_ARTIFACTS?: R2Like });
  const bytes = await store.get(`artifacts/${conversationId}/${token}`);
  if (!bytes) return Response.json({ error: "not_found" }, { status: 404 });
  // Copy into a plain ArrayBuffer: the blob store's Uint8Array is backed by a
  // shared/array-like buffer that Response's BodyInit does not accept.
  const payload = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(payload).set(bytes);
  return new Response(payload, {
    status: 200,
    headers: {
      "Content-Type": artifact.mediaType,
      "Content-Length": String(bytes.byteLength),
      "Content-Disposition": `${isViewable(artifact.mediaType) ? "inline" : "attachment"}; filename="${artifact.name.replace(/["\\]/g, "")}"`,
      "Cache-Control": "no-store, private",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
