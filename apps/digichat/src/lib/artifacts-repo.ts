/**
 * Artifact metadata persistence.
 *
 * Follows `conversations-repo.ts` exactly: every session-scoped read and write
 * first proves the conversation belongs to the caller (tenant + owner), so an
 * artifact can never be read through a conversation the caller does not own.
 *
 * The table carries `ON DELETE CASCADE` from `conversations`, which is the
 * expiry rule from the decision on DIG-2638 - ending a session removes its
 * artifacts. The *link* is session-scoped on top of that, in
 * `session-links.ts`; this module only stores state.
 */
import { and, desc, eq } from "drizzle-orm";
import type { PostgresJsDatabase } from "drizzle-orm/postgres-js";

import { artifacts, conversations } from "@/db/schema";
import type * as schema from "@/db/schema";

type Db = PostgresJsDatabase<typeof schema>;

const LIST_LIMIT = 50;

export interface ArtifactOwnership {
  conversationId: string;
  tenantId: string;
  ownerUserSub: string;
}

/**
 * The ownership guard. Returns false when the conversation is not the
 * caller's - which is also the answer for a conversation that does not exist,
 * so a missing row never reads as an authorization failure.
 */
async function ownsConversation(db: Db, params: ArtifactOwnership): Promise<boolean> {
  const conv = await db
    .select({ id: conversations.id })
    .from(conversations)
    .where(
      and(
        eq(conversations.id, params.conversationId),
        eq(conversations.tenantId, params.tenantId),
        eq(conversations.ownerUserSub, params.ownerUserSub)
      )
    )
    .limit(1);
  return conv.length > 0;
}

export interface NewArtifact {
  token: string;
  name: string;
  mediaType: string;
  byteSize: number;
  storageKey: string;
  kind?: string;
  summary?: string | null;
}

/** The metadata the model is allowed to see. Never includes a payload. */
export interface ArtifactMetadata {
  id: string;
  token: string;
  name: string;
  mediaType: string;
  byteSize: number;
  kind: string;
  summary: string | null;
  createdAt: Date;
}

export async function insertArtifact(
  db: Db,
  params: ArtifactOwnership & NewArtifact
): Promise<string | null> {
  if (!(await ownsConversation(db, params))) return null;
  const inserted = await db
    .insert(artifacts)
    .values({
      conversationId: params.conversationId,
      token: params.token,
      name: params.name,
      mediaType: params.mediaType,
      byteSize: params.byteSize,
      storageKey: params.storageKey,
      kind: params.kind ?? "file",
      summary: params.summary ?? null,
    })
    .returning({ id: artifacts.id });
  return inserted[0]?.id ?? null;
}

/**
 * Metadata only: this is the list `/artifacts` renders and the list the model
 * may be told about. It carries no artifact bytes and no rows from inside one.
 */
export async function listArtifacts(
  db: Db,
  params: ArtifactOwnership
): Promise<ArtifactMetadata[]> {
  if (!(await ownsConversation(db, params))) return [];
  return db
    .select({
      id: artifacts.id,
      token: artifacts.token,
      name: artifacts.name,
      mediaType: artifacts.mediaType,
      byteSize: artifacts.byteSize,
      kind: artifacts.kind,
      summary: artifacts.summary,
      createdAt: artifacts.createdAt,
    })
    .from(artifacts)
    .where(eq(artifacts.conversationId, params.conversationId))
    .orderBy(desc(artifacts.createdAt))
    .limit(LIST_LIMIT);
}

/**
 * Resolve a link token to its artifact, only when the caller owns the
 * conversation it belongs to. This is the read that a session-scoped link
 * performs, so it takes the session id as part of the guard.
 */
export async function getArtifactByToken(
  db: Db,
  params: ArtifactOwnership & { token: string }
): Promise<ArtifactMetadata | null> {
  if (!(await ownsConversation(db, params))) return null;
  const rows = await db
    .select({
      id: artifacts.id,
      token: artifacts.token,
      name: artifacts.name,
      mediaType: artifacts.mediaType,
      byteSize: artifacts.byteSize,
      kind: artifacts.kind,
      summary: artifacts.summary,
      createdAt: artifacts.createdAt,
      storageKey: artifacts.storageKey,
      conversationId: artifacts.conversationId,
    })
    .from(artifacts)
    .where(and(eq(artifacts.token, params.token), eq(artifacts.conversationId, params.conversationId)))
    .limit(1);
  const row = rows[0];
  if (!row) return null;
  const { storageKey: _storageKey, conversationId: _conversationId, ...metadata } = row;
  return metadata;
}

export async function deleteArtifact(
  db: Db,
  params: ArtifactOwnership & { token: string }
): Promise<string | null> {
  if (!(await ownsConversation(db, params))) return null;
  const removed = await db
    .delete(artifacts)
    .where(
      and(eq(artifacts.token, params.token), eq(artifacts.conversationId, params.conversationId))
    )
    .returning({ storageKey: artifacts.storageKey });
  return removed[0]?.storageKey ?? null;
}
