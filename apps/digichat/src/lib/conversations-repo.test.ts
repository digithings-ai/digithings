import { describe, expect, it, vi } from "vitest";
import { replaceConversationMessages } from "@/lib/conversations-repo";

describe("replaceConversationMessages", () => {
  it("wraps delete, insert, and update in a transaction", async () => {
    const tx = {
      delete: vi.fn().mockReturnValue({
        where: vi.fn().mockResolvedValue(undefined),
      }),
      insert: vi.fn().mockReturnValue({ values: vi.fn().mockResolvedValue(undefined) }),
      update: vi.fn().mockReturnValue({
        set: vi.fn().mockReturnValue({
          where: vi.fn().mockResolvedValue(undefined),
        }),
      }),
      select: vi.fn().mockReturnValue({
        from: vi.fn().mockReturnValue({
          where: vi.fn().mockResolvedValue([{ value: 0 }]),
        }),
      }),
    };
    const db = {
      select: vi.fn().mockReturnValue({
        from: vi.fn().mockReturnValue({
          where: vi.fn().mockReturnValue({
            limit: vi.fn().mockResolvedValue([{ id: "conv-1" }]),
          }),
        }),
      }),
      transaction: vi.fn(async (fn: (inner: typeof tx) => Promise<unknown>) => {
        return await fn(tx);
      }),
    };

    const ok = await replaceConversationMessages(db as never, {
      conversationId: "conv-1",
      tenantId: "tenant-1",
      ownerUserSub: "user-1",
      messages: [{ id: "m1", role: "user", parts: [] }],
      title: "T",
    });

    expect(ok).toBe("ok");
    expect(db.transaction).toHaveBeenCalledTimes(1);
    expect(tx.delete).toHaveBeenCalled();
    expect(tx.insert).toHaveBeenCalled();
    expect(tx.update).toHaveBeenCalled();
  });

  it("refuses a shrinking PUT without allowTruncate", async () => {
    const tx = {
      delete: vi.fn(),
      insert: vi.fn(),
      update: vi.fn(),
      select: vi.fn().mockReturnValue({
        from: vi.fn().mockReturnValue({
          where: vi.fn().mockResolvedValue([{ value: 5 }]),
        }),
      }),
    };
    const db = {
      select: vi.fn().mockReturnValue({
        from: vi.fn().mockReturnValue({
          where: vi.fn().mockReturnValue({
            limit: vi.fn().mockResolvedValue([{ id: "conv-1" }]),
          }),
        }),
      }),
      transaction: vi.fn(async (fn: (inner: typeof tx) => Promise<unknown>) => {
        return await fn(tx);
      }),
    };

    const result = await replaceConversationMessages(db as never, {
      conversationId: "conv-1",
      tenantId: "tenant-1",
      ownerUserSub: "user-1",
      messages: [{ id: "m1", role: "user", parts: [] }],
    });

    expect(result).toBe("would_truncate");
    expect(tx.delete).not.toHaveBeenCalled();
    expect(tx.insert).not.toHaveBeenCalled();
  });

  it("allows intentional truncate when allowTruncate is set", async () => {
    const tx = {
      delete: vi.fn().mockReturnValue({
        where: vi.fn().mockResolvedValue(undefined),
      }),
      insert: vi.fn(),
      update: vi.fn().mockReturnValue({
        set: vi.fn().mockReturnValue({
          where: vi.fn().mockResolvedValue(undefined),
        }),
      }),
      select: vi.fn(),
    };
    const db = {
      select: vi.fn().mockReturnValue({
        from: vi.fn().mockReturnValue({
          where: vi.fn().mockReturnValue({
            limit: vi.fn().mockResolvedValue([{ id: "conv-1" }]),
          }),
        }),
      }),
      transaction: vi.fn(async (fn: (inner: typeof tx) => Promise<unknown>) => {
        return await fn(tx);
      }),
    };

    const result = await replaceConversationMessages(db as never, {
      conversationId: "conv-1",
      tenantId: "tenant-1",
      ownerUserSub: "user-1",
      messages: [],
      allowTruncate: true,
    });

    expect(result).toBe("ok");
    expect(tx.delete).toHaveBeenCalled();
    expect(tx.select).not.toHaveBeenCalled();
  });

  it("propagates transaction failure without partial writes", async () => {
    const tx = {
      delete: vi.fn().mockReturnValue({
        where: vi.fn().mockResolvedValue(undefined),
      }),
      insert: vi.fn().mockReturnValue({
        values: vi.fn().mockRejectedValue(new Error("insert failed")),
      }),
      update: vi.fn(),
      select: vi.fn().mockReturnValue({
        from: vi.fn().mockReturnValue({
          where: vi.fn().mockResolvedValue([{ value: 0 }]),
        }),
      }),
    };
    const db = {
      select: vi.fn().mockReturnValue({
        from: vi.fn().mockReturnValue({
          where: vi.fn().mockReturnValue({
            limit: vi.fn().mockResolvedValue([{ id: "conv-1" }]),
          }),
        }),
      }),
      transaction: vi.fn(async (fn: (inner: typeof tx) => Promise<unknown>) => {
        return await fn(tx);
      }),
    };

    await expect(
      replaceConversationMessages(db as never, {
        conversationId: "conv-1",
        tenantId: "tenant-1",
        ownerUserSub: "user-1",
        messages: [{ id: "m1", role: "user", parts: [] }],
      })
    ).rejects.toThrow("insert failed");

    expect(db.transaction).toHaveBeenCalledTimes(1);
    expect(tx.delete).toHaveBeenCalled();
    expect(tx.update).not.toHaveBeenCalled();
  });

  it("returns not_found when conversation is not owned", async () => {
    const db = {
      select: vi.fn().mockReturnValue({
        from: vi.fn().mockReturnValue({
          where: vi.fn().mockReturnValue({
            limit: vi.fn().mockResolvedValue([]),
          }),
        }),
      }),
      transaction: vi.fn(),
    };

    const ok = await replaceConversationMessages(db as never, {
      conversationId: "missing",
      tenantId: "tenant-1",
      ownerUserSub: "user-1",
      messages: [],
    });

    expect(ok).toBe("not_found");
    expect(db.transaction).not.toHaveBeenCalled();
  });
});
