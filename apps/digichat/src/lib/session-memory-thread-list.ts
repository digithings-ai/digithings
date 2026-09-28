/**
 * RemoteThreadListAdapter that keeps thread metadata in sessionStorage so a
 * same-tab reload restores the list. Per-thread messages live in the AI SDK
 * chat store for the tab lifetime (keyed by thread id via the runtime).
 */

import type {
  RemoteThreadListAdapter,
  RemoteThreadListResponse,
  RemoteThreadMetadata,
  RemoteThreadInitializeResponse,
} from "@assistant-ui/core";

type StoredThread = {
  remoteId: string;
  status: "regular" | "archived";
  title?: string;
  custom?: Record<string, unknown>;
};

function readStore(key: string): StoredThread[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (t): t is StoredThread =>
        !!t &&
        typeof t === "object" &&
        typeof (t as StoredThread).remoteId === "string",
    );
  } catch {
    return [];
  }
}

function writeStore(key: string, threads: StoredThread[]): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(key, JSON.stringify(threads));
  } catch {
    /* private mode / quota — in-memory list still works for this instance */
  }
}

export class SessionMemoryThreadListAdapter implements RemoteThreadListAdapter {
  private threads: StoredThread[];

  constructor(private readonly storageKey: string) {
    this.threads = readStore(storageKey);
  }

  private persist(): void {
    writeStore(this.storageKey, this.threads);
  }

  list(): Promise<RemoteThreadListResponse> {
    return Promise.resolve({
      threads: this.threads.map(
        (t): RemoteThreadMetadata => ({
          status: t.status,
          remoteId: t.remoteId,
          externalId: t.remoteId,
          title: t.title,
          custom: t.custom,
        }),
      ),
    });
  }

  rename(remoteId: string, newTitle: string): Promise<void> {
    const t = this.threads.find((x) => x.remoteId === remoteId);
    if (t) {
      t.title = newTitle;
      this.persist();
    }
    return Promise.resolve();
  }

  updateCustom(
    remoteId: string,
    custom: Record<string, unknown> | undefined,
  ): Promise<void> {
    const t = this.threads.find((x) => x.remoteId === remoteId);
    if (t) {
      t.custom = custom;
      this.persist();
    }
    return Promise.resolve();
  }

  archive(remoteId: string): Promise<void> {
    const t = this.threads.find((x) => x.remoteId === remoteId);
    if (t) {
      t.status = "archived";
      this.persist();
    }
    return Promise.resolve();
  }

  unarchive(remoteId: string): Promise<void> {
    const t = this.threads.find((x) => x.remoteId === remoteId);
    if (t) {
      t.status = "regular";
      this.persist();
    }
    return Promise.resolve();
  }

  delete(remoteId: string): Promise<void> {
    this.threads = this.threads.filter((t) => t.remoteId !== remoteId);
    this.persist();
    return Promise.resolve();
  }

  initialize(threadId: string): Promise<RemoteThreadInitializeResponse> {
    if (!this.threads.some((t) => t.remoteId === threadId)) {
      this.threads.unshift({
        remoteId: threadId,
        status: "regular",
        title: "New chat",
      });
      this.persist();
    }
    return Promise.resolve({ remoteId: threadId, externalId: threadId });
  }

  generateTitle(): Promise<ReadableStream> {
    return Promise.resolve(
      new ReadableStream({
        start(controller) {
          controller.close();
        },
      }),
    );
  }

  fetch(threadId: string): Promise<RemoteThreadMetadata> {
    const t = this.threads.find((x) => x.remoteId === threadId);
    if (!t) {
      return Promise.reject(
        new Error(`Thread "${threadId}" not found in session memory list.`),
      );
    }
    return Promise.resolve({
      status: t.status,
      remoteId: t.remoteId,
      externalId: t.remoteId,
      title: t.title,
      custom: t.custom,
    });
  }
}

export function memoryThreadStorageKey(host: string, userId?: string): string {
  return `digichat:memory-threads:${host}:${userId ?? "anon"}`;
}
