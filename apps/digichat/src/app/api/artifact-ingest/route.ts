/**
 * `/api/artifact-ingest` - the one door an MCP server hands oversized rows
 * through, into the artifact store.
 *
 * Why a separate door rather than the conversation-scoped `/artifacts` POST:
 * that route derives its identity from the *caller's* session, and an MCP
 * server inside the stack has none. This route authenticates a bearer grant,
 * takes the conversation id explicitly, and then re-checks conversation
 * ownership through exactly the same `insertArtifact` guard the browser path
 * uses. A grant therefore cannot write into a conversation it does not belong
 * to: it names the conversation, and `artifacts-repo.ts` decides whether that
 * naming is true.
 *
 * What the grant is not: it is not an object-store key, not a database
 * credential, and not a bearer for any other surface. The MCP container holds
 * nothing that could write anywhere else.
 *
 * The response carries a *link*, not bytes. The link is bound to the live
 * session here (`bindLink`) and resolves through
 * `/conversations/[id]/artifacts/blob`, which re-checks the session before it
 * serves a byte. Nothing in this file expires on a clock: the artifact dies
 * with its conversation (`ON DELETE CASCADE`), and the link stops validating
 * when the session does.
 */
import { getDb } from "@/db";
import { insertArtifact } from "@/lib/artifacts-repo";
import {
  createFileBlobStore,
  createR2BlobStore,
  defaultFileBlobRoot,
  type ArtifactBlobStore,
  type R2Like,
} from "@/lib/artifact-blobs";
import { requireDigiChatAuth } from "@/lib/request-auth";
import { tenantIdBySlug } from "@/lib/conversations-repo";
import { bindLink, registerSession } from "@/lib/session-links";

/** Mirrors the ceiling in the conversation-scoped route: one 25 MiB write. */
const MAX_ARTIFACT_BYTES = 25 * 1024 * 1024;

function blobStore(env: { DIGICHAT_ARTIFACTS?: R2Like }): ArtifactBlobStore {
  const bucket = env.DIGICHAT_ARTIFACTS;
  if (bucket && typeof bucket.put === "function") return createR2BlobStore(bucket);
  return createFileBlobStore(defaultFileBlobRoot());
}

/** Same storage-key shape as the conversation-scoped route. */
function storageKeyFor(conversationId: string, token: string): string {
  return `artifacts/${conversationId}/${token}`;
}

export async function POST(req: Request) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;
  const db = getDb();
  if (!db) return Response.json({ error: "database_unavailable" }, { status: 503 });
  const tenantId = await tenantIdBySlug(db, authCtx.tenantSlug);
  if (!tenantId) return Response.json({ error: "tenant_not_found" }, { status: 404 });

  let body: {
    conversationId?: unknown;
    token?: unknown;
    name?: unknown;
    mediaType?: unknown;
    kind?: unknown;
    summary?: unknown;
    bytes?: unknown;
  };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return Response.json({ error: "invalid_json" }, { status: 400 });
  }

  if (
    typeof body.conversationId !== "string" ||
    !body.conversationId.trim() ||
    typeof body.token !== "string" ||
    !body.token.trim() ||
    typeof body.name !== "string" ||
    !body.name.trim() ||
    typeof body.mediaType !== "string" ||
    !body.mediaType.trim()
  ) {
    return Response.json({ error: "invalid_body" }, { status: 400 });
  }
  if (!Array.isArray(body.bytes) && !(body.bytes instanceof Uint8Array)) {
    return Response.json({ error: "invalid_body" }, { status: 400 });
  }
  const bytes = new Uint8Array(body.bytes as number[] | Uint8Array);
  if (bytes.byteLength === 0 || bytes.byteLength > MAX_ARTIFACT_BYTES) {
    return Response.json({ error: "invalid_body" }, { status: 400 });
  }

  const conversationId = body.conversationId.trim();
  const token = body.token.trim();
  // The grant names one conversation. A header that disagrees with the body is
  // not a detail to reconcile - it is a request to write somewhere else.
  const headerConversation = req.headers.get("x-conversation-id")?.trim();
  if (headerConversation && headerConversation !== conversationId) {
    return Response.json({ error: "conversation_mismatch" }, { status: 400 });
  }

  const store = blobStore(process.env as { DIGICHAT_ARTIFACTS?: R2Like });
  const storageKey = storageKeyFor(conversationId, token);
  const mediaType = body.mediaType.trim();
  try {
    await store.put(storageKey, bytes, mediaType);
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
    kind: typeof body.kind === "string" && body.kind.trim() ? body.kind.trim() : "file",
    // The producer sends the summary already serialised; the column is text.
    summary:
      typeof body.summary === "string" && body.summary.trim()
        ? body.summary.trim()
        : typeof body.summary === "object" && body.summary !== null
          ? JSON.stringify(body.summary)
          : null,
  });

  if (!id) {
    // Ownership failed. Drop the bytes we just wrote rather than leave an
    // orphan blob no row points at.
    await store.delete(storageKey).catch(() => {});
    return Response.json({ error: "not_found" }, { status: 404 });
  }

  // Bind the link to the live session. `registerSession` is idempotent for the
  // same id, so a re-ingest into the same conversation keeps its links; a
  // reload that re-registers under a new id retires this one.
  registerSession(conversationId, authCtx.ownerUserSub);
  bindLink(conversationId, token);

  return Response.json(
    { id, storageKey, link: `/api/conversations/${conversationId}/artifacts/blob?token=${token}` },
    { status: 201 }
  );
}
