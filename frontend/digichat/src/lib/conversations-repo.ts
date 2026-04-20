import { and, desc, eq } from "drizzle-orm";
import type { UIMessage } from "ai";
import type { PostgresJsDatabase } from "drizzle-orm/postgres-js";
import {
  conversationMessages,
  conversations,
  quantRuns,
  tenants,
} from "@/db/schema";
import type * as schema from "@/db/schema";

type Db = PostgresJsDatabase<typeof schema>;

export async function tenantIdBySlug(db: Db, slug: string): Promise<string | null> {
  const row = await db
    .select({ id: tenants.id })
    .from(tenants)
    .where(eq(tenants.slug, slug))
    .limit(1);
  return row[0]?.id ?? null;
}

export async function listConversationSummaries(
  db: Db,
  tenantId: string,
  ownerUserSub: string
): Promise<{ id: string; title: string; updatedAt: Date }[]> {
  return db
    .select({
      id: conversations.id,
      title: conversations.title,
      updatedAt: conversations.updatedAt,
    })
    .from(conversations)
    .where(
      and(
        eq(conversations.tenantId, tenantId),
        eq(conversations.ownerUserSub, ownerUserSub)
      )
    )
    .orderBy(desc(conversations.updatedAt))
    .limit(200);
}

export async function getConversationMessages(
  db: Db,
  conversationId: string,
  tenantId: string,
  ownerUserSub: string
): Promise<{ title: string; messages: UIMessage[] } | null> {
  const conv = await db
    .select({
      title: conversations.title,
    })
    .from(conversations)
    .where(
      and(
        eq(conversations.id, conversationId),
        eq(conversations.tenantId, tenantId),
        eq(conversations.ownerUserSub, ownerUserSub)
      )
    )
    .limit(1);

  if (!conv.length) return null;

  const rows = await db
    .select({
      sequence: conversationMessages.sequence,
      payload: conversationMessages.payload,
    })
    .from(conversationMessages)
    .where(eq(conversationMessages.conversationId, conversationId))
    .orderBy(conversationMessages.sequence);

  const messages = rows.map((r) => r.payload as unknown as UIMessage);
  return { title: conv[0].title, messages };
}

export async function createConversation(
  db: Db,
  params: {
    tenantId: string;
    ownerUserSub: string;
    id?: string;
    title?: string;
  }
): Promise<string> {
  const id = params.id?.trim() || crypto.randomUUID();
  await db.insert(conversations).values({
    id,
    tenantId: params.tenantId,
    ownerUserSub: params.ownerUserSub,
    title: params.title?.trim() || "New chat",
  });
  return id;
}

export async function replaceConversationMessages(
  db: Db,
  params: {
    conversationId: string;
    tenantId: string;
    ownerUserSub: string;
    title?: string;
    messages: UIMessage[];
  }
): Promise<boolean> {
  const ok = await db
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

  if (!ok.length) return false;

  await db
    .delete(conversationMessages)
    .where(eq(conversationMessages.conversationId, params.conversationId));

  if (params.messages.length > 0) {
    await db.insert(conversationMessages).values(
      params.messages.map((m, sequence) => ({
        conversationId: params.conversationId,
        sequence,
        payload: { ...m } as Record<string, unknown>,
      }))
    );
  }

  await db
    .update(conversations)
    .set({
      updatedAt: new Date(),
      ...(params.title !== undefined ? { title: params.title } : {}),
    })
    .where(eq(conversations.id, params.conversationId));

  return true;
}

export async function updateConversationTitle(
  db: Db,
  params: {
    conversationId: string;
    tenantId: string;
    ownerUserSub: string;
    title: string;
  }
): Promise<boolean> {
  const res = await db
    .update(conversations)
    .set({ title: params.title, updatedAt: new Date() })
    .where(
      and(
        eq(conversations.id, params.conversationId),
        eq(conversations.tenantId, params.tenantId),
        eq(conversations.ownerUserSub, params.ownerUserSub)
      )
    )
    .returning({ id: conversations.id });

  return res.length > 0;
}

export async function deleteConversation(
  db: Db,
  params: {
    conversationId: string;
    tenantId: string;
    ownerUserSub: string;
  }
): Promise<boolean> {
  const res = await db
    .delete(conversations)
    .where(
      and(
        eq(conversations.id, params.conversationId),
        eq(conversations.tenantId, params.tenantId),
        eq(conversations.ownerUserSub, params.ownerUserSub)
      )
    )
    .returning({ id: conversations.id });

  return res.length > 0;
}

export async function listQuantRuns(
  db: Db,
  params: {
    conversationId: string;
    tenantId: string;
    ownerUserSub: string;
  }
): Promise<
  {
    id: string;
    label: string;
    strategyName: string;
    symbols: string[];
    strategyParams: Record<string, unknown> | null;
    backtestResult: Record<string, unknown>;
    createdAt: Date;
  }[]
> {
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
  if (!conv.length) return [];

  return db
    .select({
      id: quantRuns.id,
      label: quantRuns.label,
      strategyName: quantRuns.strategyName,
      symbols: quantRuns.symbols,
      strategyParams: quantRuns.strategyParams,
      backtestResult: quantRuns.backtestResult,
      createdAt: quantRuns.createdAt,
    })
    .from(quantRuns)
    .where(eq(quantRuns.conversationId, params.conversationId))
    .orderBy(desc(quantRuns.createdAt))
    .limit(50);
}

export async function insertQuantRun(
  db: Db,
  params: {
    conversationId: string;
    tenantId: string;
    ownerUserSub: string;
    label?: string;
    strategyName: string;
    symbols: string[];
    strategyParams?: Record<string, unknown> | null;
    backtestResult: Record<string, unknown>;
  }
): Promise<string | null> {
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
  if (!conv.length) return null;

  const inserted = await db
    .insert(quantRuns)
    .values({
      conversationId: params.conversationId,
      label: params.label?.trim() || "Backtest",
      strategyName: params.strategyName,
      symbols: params.symbols,
      strategyParams: params.strategyParams ?? null,
      backtestResult: params.backtestResult,
    })
    .returning({ id: quantRuns.id });

  return inserted[0]?.id ?? null;
}
