import type { UIMessage } from "ai";
import { logStorageFailure } from "@/lib/storage-debug";

export const THREAD_LOCAL_VERSION = 1;

export type ChatThreadState = {
  id: string;
  title: string;
  updatedAt: string;
  messages: UIMessage[];
  /** Row exists on server (Postgres). */
  remote: boolean;
  /**
   * Authoritative message list is safe to PUT to the server.
   * Remote threads start false until a successful GET (or local cache had messages).
   * PUT is a full replace — flushing while false would wipe Postgres history.
   */
  hydrated: boolean;
  /** Bump to remount `useChat` after async load of server messages. */
  hydrateVersion: number;
};

/**
 * `PUT /api/conversations/[id]` deletes then re-inserts every message.
 * Never flush a remote thread whose body has not been loaded yet — an empty
 * (or newly typed) client array would permanently erase the server history.
 */
export function canFlushServerMessages(t: Pick<ChatThreadState, "remote" | "hydrated">): boolean {
  return !t.remote || t.hydrated;
}

/** Apply a successful GET /api/conversations/[id] payload onto thread state. */
export function withHydratedConversation(
  t: ChatThreadState,
  payload: { title: string; messages: UIMessage[] }
): ChatThreadState {
  return {
    ...t,
    title: payload.title,
    messages: payload.messages,
    hydrated: true,
    hydrateVersion: t.hydrateVersion + 1,
  };
}

type LocalPersistedThread = {
  id: string;
  title: string;
  updatedAt: string;
  messages: UIMessage[];
};

type LocalBlob = {
  v: number;
  threads: LocalPersistedThread[];
};

export function localStorageKey(ownerKey: string): string {
  return `digichat-threads:${ownerKey}`;
}

export function loadLocalThreads(ownerKey: string): LocalPersistedThread[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(localStorageKey(ownerKey));
    if (!raw) return [];
    const j = JSON.parse(raw) as LocalBlob;
    if (j.v !== THREAD_LOCAL_VERSION || !Array.isArray(j.threads)) return [];
    return j.threads;
  } catch (err) {
    logStorageFailure("loadLocalThreads", err);
    return [];
  }
}

export function saveLocalThreads(
  ownerKey: string,
  threads: ChatThreadState[] | LocalPersistedThread[]
): void {
  if (typeof window === "undefined") return;
  const persisted: LocalPersistedThread[] = threads.map((t) => ({
    id: t.id,
    title: t.title,
    updatedAt: t.updatedAt,
    messages: t.messages,
  }));
  const blob: LocalBlob = { v: THREAD_LOCAL_VERSION, threads: persisted };
  try {
    window.localStorage.setItem(localStorageKey(ownerKey), JSON.stringify(blob));
  } catch (err) {
    logStorageFailure("saveLocalThreads", err);
  }
}

export function mergeRemoteAndLocal(
  remote: Array<{ id: string; title: string; updatedAt: string }>,
  local: LocalPersistedThread[]
): ChatThreadState[] {
  const localById = new Map(local.map((t) => [t.id, t]));
  const seen = new Set<string>();
  const out: ChatThreadState[] = [];

  for (const r of remote) {
    seen.add(r.id);
    const loc = localById.get(r.id);
    const hasLocalMessages = !!loc?.messages?.length;
    out.push({
      id: r.id,
      title: r.title,
      updatedAt: r.updatedAt,
      messages: loc?.messages ?? [],
      remote: true,
      hydrated: hasLocalMessages,
      hydrateVersion: hasLocalMessages ? 1 : 0,
    });
  }

  for (const loc of local) {
    if (!seen.has(loc.id)) {
      out.push({
        id: loc.id,
        title: loc.title,
        updatedAt: loc.updatedAt,
        messages: loc.messages,
        remote: false,
        hydrated: true,
        hydrateVersion: 1,
      });
    }
  }

  out.sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
  return out;
}
