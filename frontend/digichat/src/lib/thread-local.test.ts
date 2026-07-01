import { describe, expect, it } from "vitest";
import type { UIMessage } from "ai";
import { mergeRemoteAndLocal } from "@/lib/thread-local";

const userMsg = (text: string): UIMessage =>
  ({
    id: crypto.randomUUID(),
    role: "user",
    parts: [{ type: "text", text }],
  }) as UIMessage;

describe("mergeRemoteAndLocal", () => {
  it("prefers server title and keeps local messages when ids match", () => {
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
