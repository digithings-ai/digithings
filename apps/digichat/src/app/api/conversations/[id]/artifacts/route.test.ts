import { beforeEach, describe, expect, it, vi } from "vitest";
import { DELETE, GET, POST, serveArtifact } from "./route";
import { mockAuthCtx } from "@/test/route-auth-mock";

vi.mock("@/lib/request-auth", () => ({
  requireDigiChatAuth: vi.fn(),
}));

vi.mock("@/db", () => ({
  getDb: vi.fn(),
}));

vi.mock("@/lib/conversations-repo", () => ({
  tenantIdBySlug: vi.fn(),
}));

vi.mock("@/lib/artifacts-repo", () => ({
  insertArtifact: vi.fn(),
  listArtifacts: vi.fn(),
  getArtifactByToken: vi.fn(),
  deleteArtifact: vi.fn(),
}));

import { requireDigiChatAuth } from "@/lib/request-auth";
import { getDb } from "@/db";
import { tenantIdBySlug } from "@/lib/conversations-repo";
import {
  deleteArtifact,
  getArtifactByToken,
  insertArtifact,
  listArtifacts,
} from "@/lib/artifacts-repo";

const routeCtx = { params: Promise.resolve({ id: "conv-1" }) };
const db = {};
const artifact = {
  id: "art-1",
  token: "tok-1",
  name: "tickets.csv",
  mediaType: "text/csv",
  byteSize: 12,
  kind: "table",
  summary: "126 tickets",
  createdAt: new Date("2026-10-10T00:00:00Z"),
};

function req(body?: unknown, method = "POST"): Request {
  return new Request("http://localhost/api/conversations/conv-1/artifacts", {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

describe("/api/conversations/[id]/artifacts", () => {
  beforeEach(() => {
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(getDb).mockReturnValue(db as never);
    vi.mocked(tenantIdBySlug).mockResolvedValue("tenant-1");
    vi.mocked(listArtifacts).mockResolvedValue([artifact]);
    vi.mocked(insertArtifact).mockResolvedValue("art-1");
    vi.mocked(getArtifactByToken).mockResolvedValue(artifact);
    vi.mocked(deleteArtifact).mockResolvedValue("artifacts/conv-1/tok-1");
    vi.stubEnv("DIGICHAT_ARTIFACT_DIR", process.env.DIGICHAT_ARTIFACT_DIR ?? "/var/tmp/digichat-artifacts");
  });

  it("GET lists metadata only - no bytes reach the client payload", async () => {
    const res = await GET(
      new Request("http://localhost/api/conversations/conv-1/artifacts"),
      routeCtx
    );
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.artifacts).toHaveLength(1);
    expect(body.artifacts[0]).toMatchObject({ name: "tickets.csv", kind: "table" });
    expect(body.artifacts[0]).not.toHaveProperty("storageKey");
    expect(body.artifacts[0]).not.toHaveProperty("bytes");
  });

  it("GET marks viewable types so the client opens them in a tab", async () => {
    vi.mocked(listArtifacts).mockResolvedValue([
      artifact,
      { ...artifact, id: "art-2", mediaType: "application/octet-stream", name: "a.bin" },
      { ...artifact, id: "art-3", mediaType: "image/png", name: "chart.png" },
    ]);
    const res = await GET(
      new Request("http://localhost/api/conversations/conv-1/artifacts"),
      routeCtx
    );
    const body = await res.json();
    expect(body.artifacts.map((a: { viewable: boolean }) => a.viewable)).toEqual([true, false, true]);
  });

  it("GET returns 503 when the deployment has no Postgres", async () => {
    vi.mocked(getDb).mockReturnValue(null as never);
    const res = await GET(
      new Request("http://localhost/api/conversations/conv-1/artifacts"),
      routeCtx
    );
    expect(res.status).toBe(503);
    expect((await res.json()).error).toBe("database_unavailable");
  });

  it("GET returns 404 for an unknown tenant", async () => {
    vi.mocked(tenantIdBySlug).mockResolvedValue(null);
    const res = await GET(
      new Request("http://localhost/api/conversations/conv-1/artifacts"),
      routeCtx
    );
    expect(res.status).toBe(404);
  });

  it("POST rejects malformed bodies", async () => {
    for (const body of [
      {},
      { token: "t" },
      { token: "t", name: "n" },
      { token: "t", name: "n", mediaType: "text/csv" },
      { token: "t", name: "n", mediaType: "text/csv", bytes: [] },
    ]) {
      const res = await POST(req(body), routeCtx);
      expect(res.status).toBe(400);
    }
  });

  it("POST rejects a body that is not JSON", async () => {
    const res = await POST(
      new Request("http://localhost/api/conversations/conv-1/artifacts", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: "{not json",
      }),
      routeCtx
    );
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe("invalid_json");
  });

  it("POST rejects a payload over the size cap", async () => {
    const bytes = new Array(25 * 1024 * 1024 + 1).fill(0);
    const res = await POST(
      req({ token: "tok-1", name: "big.csv", mediaType: "text/csv", bytes }),
      routeCtx
    );
    expect(res.status).toBe(400);
  });

  it("POST stores bytes then records metadata", async () => {
    const res = await POST(
      req({
        token: "tok-1",
        name: "tickets.csv",
        mediaType: "text/csv",
        bytes: [104, 101, 108, 108, 111],
        summary: "126 tickets",
      }),
      routeCtx
    );
    expect(res.status).toBe(201);
    expect(await res.json()).toMatchObject({ id: "art-1", storageKey: "artifacts/conv-1/tok-1" });
    expect(insertArtifact).toHaveBeenCalledWith(
      db,
      expect.objectContaining({
        conversationId: "conv-1",
        token: "tok-1",
        byteSize: 5,
        kind: "table",
        summary: "126 tickets",
      })
    );
  });

  it("POST drops the bytes when the conversation is not the caller's", async () => {
    vi.mocked(insertArtifact).mockResolvedValue(null);
    const res = await POST(
      req({ token: "tok-1", name: "tickets.csv", mediaType: "text/csv", bytes: [104] }),
      routeCtx
    );
    expect(res.status).toBe(404);
  });

  it("DELETE requires a token", async () => {
    const res = await DELETE(
      new Request("http://localhost/api/conversations/conv-1/artifacts", { method: "DELETE" }),
      routeCtx
    );
    expect(res.status).toBe(400);
  });

  it("DELETE removes the row and reports 404 when the caller does not own it", async () => {
    vi.mocked(deleteArtifact).mockResolvedValue(null);
    const res = await DELETE(
      new Request("http://localhost/api/conversations/conv-1/artifacts?token=tok-1", {
        method: "DELETE",
      }),
      routeCtx
    );
    expect(res.status).toBe(404);
  });

  it("serves an artifact inline when the type is viewable", async () => {
    // Write the bytes first: serving reads the same blob store the write used.
    const written = await POST(
      req({ token: "tok-1", name: "tickets.csv", mediaType: "text/csv", bytes: [104, 105] }),
      routeCtx
    );
    expect(written.status).toBe(201);
    const res = await serveArtifact(
      new Request("http://localhost/api/conversations/conv-1/artifacts/blob"),
      { ...routeCtx, token: "tok-1" }
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/csv");
    expect(res.headers.get("Content-Disposition")).toContain("inline");
    expect(res.headers.get("Cache-Control")).toBe("no-store, private");
    expect(await res.text()).toBe("hi");
  });

  it("downloads rather than inlines an unknown type", async () => {
    vi.mocked(getArtifactByToken).mockResolvedValue({
      ...artifact,
      mediaType: "application/octet-stream",
      name: "blob.bin",
    });
    await POST(
      req({ token: "tok-2", name: "blob.bin", mediaType: "application/octet-stream", bytes: [1] }),
      routeCtx
    );
    const res = await serveArtifact(
      new Request("http://localhost/api/conversations/conv-1/artifacts/blob"),
      { ...routeCtx, token: "tok-2" }
    );
    expect(res.headers.get("Content-Disposition")).toContain("attachment");
  });

  it("serving an unknown token is 404, not an empty 200", async () => {
    vi.mocked(getArtifactByToken).mockResolvedValue(null);
    const res = await serveArtifact(
      new Request("http://localhost/api/conversations/conv-1/artifacts/blob"),
      { ...routeCtx, token: "nope" }
    );
    expect(res.status).toBe(404);
  });
});
