import { describe, expect, it, vi } from "vitest";
import {
  deleteArtifact,
  getArtifactByToken,
  insertArtifact,
  listArtifacts,
} from "@/lib/artifacts-repo";

const OWNER = { conversationId: "conv-1", tenantId: "tenant-1", ownerUserSub: "user-1" };

const ROW = {
  id: "art-1",
  token: "tok-1",
  name: "tickets.csv",
  mediaType: "text/csv",
  byteSize: 12,
  kind: "table",
  summary: "126 tickets",
  createdAt: new Date("2026-10-10T00:00:00Z"),
  storageKey: "artifacts/conv-1/tok-1",
  conversationId: "conv-1",
};

/**
 * Chainable drizzle stand-in in the same shape as `conversations-repo.test.ts`.
 * `owned` drives the ownership guard, so every case can assert what happens
 * when the conversation is not the caller's.
 */
function fakeDb(options: { owned?: boolean; selectRows?: unknown[]; returning?: unknown[] } = {}) {
  const owned = options.owned ?? true;
  const selectRows = options.selectRows ?? [{ id: "conv-1" }];
  const returningRows = options.returning ?? [{ id: "art-1" }];
  const select = vi.fn(() => ({
    from: () => ({
      where: () => ({
        limit: async () => (owned ? selectRows : []),
        orderBy: () => ({ limit: async () => selectRows }),
      }),
    }),
  }));
  const insert = vi.fn(() => ({
    values: () => ({ returning: async () => returningRows }),
  }));
  const remove = vi.fn(() => ({
    where: () => ({ returning: async () => (owned ? returningRows : []) }),
  }));
  const db = { select, insert, delete: remove };
  return { db: db as never, select, insert, remove };
}

describe("artifacts-repo ownership guard", () => {
  it("listArtifacts returns metadata only, never a storage key", async () => {
    const { db } = fakeDb({ selectRows: [ROW] });
    const rows = await listArtifacts(db, OWNER);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ token: "tok-1", kind: "table" });
    expect(rows[0]).not.toHaveProperty("storageKey");
    expect(rows[0]).not.toHaveProperty("conversationId");
  });

  it("listArtifacts returns nothing for a conversation the caller does not own", async () => {
    const { db } = fakeDb({ owned: false });
    expect(await listArtifacts(db, OWNER)).toEqual([]);
  });

  it("insertArtifact refuses when the caller does not own the conversation", async () => {
    const { db, insert } = fakeDb({ owned: false });
    const id = await insertArtifact(db, {
      ...OWNER,
      token: "tok-1",
      name: "tickets.csv",
      mediaType: "text/csv",
      byteSize: 12,
      storageKey: "artifacts/conv-1/tok-1",
    });
    expect(id).toBeNull();
    expect(insert).not.toHaveBeenCalled();
  });

  it("insertArtifact records metadata and returns the row id", async () => {
    const { db, insert } = fakeDb();
    const id = await insertArtifact(db, {
      ...OWNER,
      token: "tok-1",
      name: "tickets.csv",
      mediaType: "text/csv",
      byteSize: 12,
      storageKey: "artifacts/conv-1/tok-1",
      kind: "table",
      summary: "126 tickets",
    });
    expect(id).toBe("art-1");
    expect(insert).toHaveBeenCalledTimes(1);
    const values = insert.mock.results[0].value;
    expect(values).toBeDefined();
  });

  it("insertArtifact defaults kind to file and summary to null", async () => {
    const captured: Record<string, unknown>[] = [];
    const db = {
      select: () => ({
        from: () => ({ where: () => ({ limit: async () => [{ id: "conv-1" }] }) }),
      }),
      insert: () => ({
        values: (v: Record<string, unknown>) => {
          captured.push(v);
          return { returning: async () => [{ id: "art-1" }] };
        },
      }),
    } as never;
    await insertArtifact(db, {
      ...OWNER,
      token: "tok-1",
      name: "notes.md",
      mediaType: "text/markdown",
      byteSize: 9,
      storageKey: "artifacts/conv-1/tok-1",
    });
    expect(captured[0]).toMatchObject({ kind: "file", summary: null });
  });
});

describe("artifacts-repo token lookup", () => {
  it("getArtifactByToken hides the storage key from callers", async () => {
    const { db } = fakeDb({ selectRows: [ROW] });
    const found = await getArtifactByToken(db, { ...OWNER, token: "tok-1" });
    expect(found).not.toBeNull();
    expect(found).toMatchObject({ id: "art-1", token: "tok-1" });
    expect(found).not.toHaveProperty("storageKey");
  });

  it("getArtifactByToken returns null for a caller who does not own it", async () => {
    const { db } = fakeDb({ owned: false, selectRows: [ROW] });
    expect(await getArtifactByToken(db, { ...OWNER, token: "tok-1" })).toBeNull();
  });

  it("getArtifactByToken returns null when the token matches nothing", async () => {
    const { db } = fakeDb({ selectRows: [] });
    expect(await getArtifactByToken(db, { ...OWNER, token: "nope" })).toBeNull();
  });
});

describe("artifacts-repo delete", () => {
  it("returns the storage key so the blob can be removed too", async () => {
    const { db } = fakeDb({ returning: [{ storageKey: "artifacts/conv-1/tok-1" }] });
    expect(await deleteArtifact(db, { ...OWNER, token: "tok-1" })).toBe("artifacts/conv-1/tok-1");
  });

  it("returns null and deletes nothing when the caller does not own it", async () => {
    const { db, remove } = fakeDb({ owned: false, returning: [{ storageKey: "x" }] });
    expect(await deleteArtifact(db, { ...OWNER, token: "tok-1" })).toBeNull();
    expect(remove).not.toHaveBeenCalled();
  });
});
