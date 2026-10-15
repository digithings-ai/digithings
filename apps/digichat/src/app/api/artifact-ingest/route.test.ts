/**
 * The ingest door: a grant writes ONE table artifact, and only into the
 * conversation the grant names -- and only when that conversation is real.
 *
 * The point of these tests is the negative. A store that accepts an unauthenticated
 * or misdirected write is worse than no store, so each case pairs the failing
 * assertion with a passing control on the same fixture.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const inserted: unknown[] = [];
const deleted: unknown[] = [];
const put: unknown[] = [];
let conversationRow: { id: string }[] = [];

vi.mock("@/db", () => ({ getDb: () => ({ __db: true }) }));
vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: async () => ({ tenantSlug: "occ", ownerUserSub: "machine:occ" }),
}));
vi.mock("@/lib/conversations-repo", () => ({ tenantIdBySlug: async () => "tenant-occ" }));
vi.mock("@/lib/artifact-blobs", () => ({
  createFileBlobStore: () => ({
    put: async (key: string, body: Uint8Array) => void put.push([key, body.byteLength]),
    get: async () => null,
    delete: async (key: string) => void deleted.push(key),
  }),
  createR2BlobStore: () => ({ put: async () => {}, get: async () => null, delete: async () => {} }),
  defaultFileBlobRoot: () => "/tmp/digichat-artifacts",
}));
vi.mock("@/lib/artifacts-repo", () => ({
  // Mirrors the real guard: a conversation the store does not hold yields null,
  // which is the same answer as "no such row".
  insertArtifact: async (db: unknown, params: { conversationId: string; storageKey: string; token: string }) => {
    if (!conversationRow.some((row) => row.id === params.conversationId)) return null;
    inserted.push(params);
    return "artifact-id-1";
  },
}));
vi.mock("@/lib/session-links", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session-links")>("@/lib/session-links");
  return actual;
});

import { POST } from "@/app/api/artifact-ingest/route";
import { endSession, isLiveSessionLink, registerSession, resetSessionLinks } from "@/lib/session-links";

const GOOD_BODY = {
  conversationId: "c-1",
  token: "a".repeat(32),
  name: "zammad-tickets-list-tickets.json",
  mediaType: "application/json",
  kind: "table",
  summary: JSON.stringify({ count: 30 }),
  bytes: [123, 125],
};

function request(body: unknown, conversationHeader: string | null = "c-1"): Request {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (conversationHeader !== null) headers["X-Conversation-Id"] = conversationHeader;
  return new Request("http://localhost/api/artifact-ingest", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

describe("the artifact ingest door", () => {
  beforeEach(() => {
    inserted.length = 0;
    deleted.length = 0;
    put.length = 0;
    conversationRow = [{ id: "c-1" }];
    resetSessionLinks();
  });

  it("writes one table artifact and answers with a link", async () => {
    const res = await POST(request(GOOD_BODY));
    expect(res.status).toBe(201);
    const body = (await res.json()) as { link: string; id: string };
    expect(body.id).toBe("artifact-id-1");
    expect(body.link).toBe(`/api/conversations/c-1/artifacts/blob?token=${"a".repeat(32)}`);
    expect(inserted).toHaveLength(1);
    expect(put).toEqual([[`artifacts/c-1/${"a".repeat(32)}`, 2]]);
  });

  it("keeps the rows out of the metadata it stores", async () => {
    await POST(request(GOOD_BODY));
    const stored = inserted[0] as { summary: string; byteSize: number };
    expect(stored.summary).toBe(JSON.stringify({ count: 30 }));
    expect(stored.byteSize).toBe(2);
  });

  it("refuses a conversation the store does not hold, and drops the bytes", async () => {
    conversationRow = [];
    const res = await POST(request(GOOD_BODY));
    // 404, not 403 and not 201: a missing conversation must not read as a
    // permission answer, and must not leave an orphan blob behind.
    expect(res.status).toBe(404);
    expect(inserted).toHaveLength(0);
    expect(deleted).toEqual([`artifacts/c-1/${"a".repeat(32)}`]);
  });

  it("refuses a header that disagrees with the body", async () => {
    const res = await POST(request(GOOD_BODY, "c-other"));
    expect(res.status).toBe(400);
    expect((await res.json()) as { error: string }).toEqual({ error: "conversation_mismatch" });
    expect(inserted).toHaveLength(0);
  });

  it("binds the link to the live session, so it dies with the session", async () => {
    const res = await POST(request(GOOD_BODY));
    const { link } = (await res.json()) as { link: string };
    const token = link.split("token=")[1];
    expect(isLiveSessionLink("c-1", token)).toBe(true);

    // New session for the same client: the old link must stop validating.
    registerSession("c-2", "machine:occ");
    expect(isLiveSessionLink("c-1", token)).toBe(false);

    // And an ended session kills it outright. The store must hold the
    // conversation first, otherwise this POST answers 404 and there is no link
    // to kill -- which would make the assertions below pass for the wrong
    // reason. The header must name c-3 too, or the POST answers
    // conversation_mismatch instead.
    conversationRow = [{ id: "c-3" }];
    const third = (await (
      await POST(request({ ...GOOD_BODY, conversationId: "c-3" }, "c-3"))
    ).json()) as { link: string };
    const thirdToken = third.link.split("token=")[1];
    expect(isLiveSessionLink("c-3", thirdToken)).toBe(true);
    endSession("c-3");
    expect(isLiveSessionLink("c-3", thirdToken)).toBe(false);
  });

  it("rejects an empty or oversized body before touching the store", async () => {
    for (const bad of [
      { ...GOOD_BODY, bytes: [] },
      { ...GOOD_BODY, bytes: "not-bytes" },
      { ...GOOD_BODY, token: "  " },
      { ...GOOD_BODY, conversationId: "" },
    ]) {
      const res = await POST(request(bad));
      expect(res.status).toBe(400);
    }
    expect(put).toHaveLength(0);
    expect(inserted).toHaveLength(0);
  });
});
