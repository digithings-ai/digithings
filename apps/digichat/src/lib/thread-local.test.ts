import { describe, expect, it } from "vitest";
import type { UIMessage } from "ai";
import {
  canFlushServerMessages,
  localCacheIsAuthoritative,
  mergeRemoteAndLocal,
  withHydratedConversation,
  type ChatThreadState,
} from "@/lib/thread-local";

const userMsg = (text: string): UIMessage =>
  ({
    id: crypto.randomUUID(),
    role: "user",
    parts: [{ type: "text", text }],
  }) as UIMessage;

describe("mergeRemoteAndLocal", () => {
  it("trusts local messages only when local updatedAt is at least as fresh as server", () => {
    const merged = mergeRemoteAndLocal(
      [
        {
          id: "a",
          title: "Server title",
          updatedAt: "2025-01-01T00:00:00.000Z",
        },
      ],
      [
        {
          id: "a",
          title: "Local old",
          updatedAt: "2025-01-01T00:00:00.000Z",
          messages: [userMsg("hello")],
        },
      ]
    );
    expect(merged).toHaveLength(1);
    expect(merged[0].title).toBe("Server title");
    expect(merged[0].messages).toHaveLength(1);
    expect(merged[0].remote).toBe(true);
    expect(merged[0].hydrated).toBe(true);
    expect(merged[0].hydrateVersion).toBe(1);
  });

  it("refuses stale local cache when server updatedAt is newer", () => {
    const merged = mergeRemoteAndLocal(
      [
        {
          id: "a",
          title: "Server title",
          updatedAt: "2025-01-02T00:00:00.000Z",
        },
      ],
      [
        {
          id: "a",
          title: "Local old",
          updatedAt: "2025-01-01T00:00:00.000Z",
          messages: [userMsg("stale")],
        },
      ]
    );
    expect(merged[0].messages).toEqual([]);
    expect(merged[0].hydrated).toBe(false);
    expect(merged[0].hydrateVersion).toBe(0);
    expect(merged[0].title).toBe("Server title");
  });

  it("marks remote threads without local messages as not hydrated", () => {
    const merged = mergeRemoteAndLocal(
      [
        {
          id: "x",
          title: "Only remote",
          updatedAt: "2025-01-02T00:00:00.000Z",
        },
      ],
      []
    );
    expect(merged[0].messages).toEqual([]);
    expect(merged[0].hydrated).toBe(false);
    expect(merged[0].hydrateVersion).toBe(0);
  });

  it("retains local-only threads", () => {
    const merged = mergeRemoteAndLocal(
      [],
      [
        {
          id: "local-1",
          title: "Offline",
          updatedAt: "2025-01-03T00:00:00.000Z",
          messages: [userMsg("ping")],
        },
      ]
    );
    expect(merged).toHaveLength(1);
    expect(merged[0].remote).toBe(false);
    expect(merged[0].id).toBe("local-1");
  });

  it("sorts by updatedAt descending", () => {
    const merged = mergeRemoteAndLocal(
      [
        {
          id: "older",
          title: "Old",
          updatedAt: "2025-01-01T00:00:00.000Z",
        },
        {
          id: "newer",
          title: "New",
          updatedAt: "2025-01-05T00:00:00.000Z",
        },
      ],
      []
    );
    expect(merged.map((m) => m.id)).toEqual(["newer", "older"]);
  });
});

describe("localCacheIsAuthoritative", () => {
  it("fails closed on unparseable timestamps", () => {
    expect(
      localCacheIsAuthoritative("not-a-date", {
        updatedAt: "2025-01-01T00:00:00.000Z",
        messages: [userMsg("x")],
      })
    ).toBe(false);
  });
});

describe("canFlushServerMessages", () => {
  it("refuses remote threads that have not been hydrated", () => {
    expect(canFlushServerMessages({ remote: true, hydrated: false })).toBe(false);
  });

  it("allows remote hydrated and local-only threads", () => {
    expect(canFlushServerMessages({ remote: true, hydrated: true })).toBe(true);
    expect(canFlushServerMessages({ remote: false, hydrated: false })).toBe(true);
    expect(canFlushServerMessages({ remote: false, hydrated: true })).toBe(true);
  });
});

describe("withHydratedConversation", () => {
  it("marks the thread hydrated and bumps hydrateVersion", () => {
    const base: ChatThreadState = {
      id: "t1",
      title: "Old",
      updatedAt: "2025-01-01T00:00:00.000Z",
      messages: [],
      remote: true,
      hydrated: false,
      hydrateVersion: 0,
    };
    const next = withHydratedConversation(base, {
      title: "Server title",
      messages: [userMsg("kept")],
    });
    expect(next.hydrated).toBe(true);
    expect(next.hydrateVersion).toBe(1);
    expect(next.title).toBe("Server title");
    expect(next.messages).toHaveLength(1);
    expect(canFlushServerMessages(next)).toBe(true);
  });
});
