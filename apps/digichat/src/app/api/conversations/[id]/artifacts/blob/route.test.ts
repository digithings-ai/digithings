/**
 * Blob-route tests. The behaviours pinned here are the ones a raw
 * `serveArtifact` cannot express:
 *
 *   1. A link bound to a live session opens (200, inline).
 *   2. A link whose session ended is 410 `session_expired`, NOT 404
 *      `not_found` - the row is still in the store and still owned, so a 404
 *      would tell the user the file never existed.
 *   3. A reload (a new conversation id for the same client) retires the old
 *      conversation's links - the real DIG-2638 rule, not a hand-set flag.
 *   4. The auth gate runs FIRST: an unauthenticated caller gets 401, never
 *      410, so link lifetime is never reported to a caller not entitled to
 *      ask about it. This is also the DoD item 4 assertion.
 *
 * Every positive test writes real bytes through `POST` first, so a 200 can
 * never be an empty-store artefact. The negatives assert *distinct* status
 * codes, so none can pass by collapsing into another.
 *
 * The session id is the conversation id (`session-links.ts`), which the route
 * reads from the path - so these tests register under `conv-1`, the same id
 * the route resolves from `params`.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";
import { POST } from "../route";
import { mockAuthCtx, unauthorizedResponse } from "@/test/route-auth-mock";

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
import { getArtifactByToken, insertArtifact } from "@/lib/artifacts-repo";
import {
  bindLink,
  endSession,
  registerSession,
  resetSessionLinks,
} from "@/lib/session-links";

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

function postReq(body: unknown): Request {
  return new Request("http://localhost/api/conversations/conv-1/artifacts", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Blob GET: the link a chat reply hands the browser. Session comes from the path. */
function blobReq(token: string, conversationId = "conv-1"): Request {
  return new Request(
    `http://localhost/api/conversations/${conversationId}/artifacts/blob?token=${encodeURIComponent(token)}`
  );
}

describe("/api/conversations/[id]/artifacts/blob", () => {
  beforeEach(() => {
    resetSessionLinks();
    vi.mocked(requireDigiChatAuth).mockResolvedValue(mockAuthCtx);
    vi.mocked(getDb).mockReturnValue(db as never);
    vi.mocked(tenantIdBySlug).mockResolvedValue("tenant-1");
    vi.mocked(insertArtifact).mockResolvedValue("art-1");
    vi.mocked(getArtifactByToken).mockResolvedValue(artifact);
    vi.stubEnv(
      "DIGICHAT_ARTIFACT_DIR",
      process.env.DIGICHAT_ARTIFACT_DIR ?? "/var/tmp/digichat-artifacts"
    );
  });

  it("serves the artifact when the link is bound to a live session", async () => {
    // Write real bytes so a 200 can never be an empty-store artefact.
    const written = await POST(
      postReq({ token: "tok-1", name: "tickets.csv", mediaType: "text/csv", bytes: [104, 105] }),
      routeCtx
    );
    expect(written.status).toBe(201);

    registerSession("conv-1");
    expect(bindLink("conv-1", "tok-1")).toBe(true);

    const res = await GET(blobReq("tok-1"), routeCtx);
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/csv");
    expect(res.headers.get("Content-Disposition")).toContain("inline");
    expect(res.headers.get("Cache-Control")).toBe("no-store, private");
    expect(await res.text()).toBe("hi");
  });

  it("a link whose session ended is 410 session_expired, not 404 not_found", async () => {
    // getArtifactByToken still resolves the row (it is owned and present):
    // only the *session* is gone. 404 would be a lie about the file.
    registerSession("conv-1");
    expect(bindLink("conv-1", "tok-1")).toBe(true);
    endSession("conv-1");

    const res = await GET(blobReq("tok-1"), routeCtx);
    expect(res.status).toBe(410);
    expect(((await res.json()) as { error: string }).error).toBe("session_expired");
    expect(res.status).not.toBe(404);
  });

  it("a reload (new conversation, same client) retires the old links", async () => {
    // The DIG-2638 rule in its real form: no TTL, links die when the client
    // presents a new conversation id under the same client key.
    registerSession("conv-1", "client-a");
    expect(bindLink("conv-1", "tok-1")).toBe(true);

    // Reload: same client key, new conversation id. This retires conv-1.
    registerSession("conv-2", "client-a");

    // The old link still points at the old conversation; it is now dead.
    const res = await GET(blobReq("tok-1"), routeCtx);
    expect(res.status).toBe(410);
    expect(((await res.json()) as { error: string }).error).toBe("session_expired");
  });

  it("the auth gate runs first: no credential -> 401, never 410", async () => {
    // DoD item 4: a link presented without the gate must fail. It fails as
    // UNAUTHORIZED (401) even though the session/link pair here IS live -
    // proving the gate is not shadowed by the lifetime check, and that link
    // lifetime is never reported to a caller not entitled to ask about it.
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    registerSession("conv-1");
    expect(bindLink("conv-1", "tok-1")).toBe(true);

    const res = await GET(blobReq("tok-1"), routeCtx);
    expect(res.status).toBe(401);
    expect(res.status).not.toBe(410);
  });

  it("a DEAD link without a credential is 401, not 410 - lifetime never leaks", async () => {
    // The discriminating half of "the gate runs first". With a live link the
    // store's own gate answers 401 anyway, so that test cannot tell the two
    // orderings apart. Here the link is NOT bound: if the route checked
    // liveness before the gate it would answer 410 and report link lifetime to
    // a caller that never passed the gate. 401 proves the gate is first.
    vi.mocked(requireDigiChatAuth).mockResolvedValue(unauthorizedResponse);
    const res = await GET(blobReq("tok-never-bound"), routeCtx);
    expect(res.status).toBe(401);
    expect(res.status).not.toBe(410);
  });

  it("a LIVE link whose row is gone is the store's own 404, not 410", async () => {
    // Keeps 410 honest: 410 is specifically a dead LINK (never bound, or the
    // session ended). A link bound to a live session whose row the store
    // cannot resolve is `not_found` - the distinction the route exists for.
    registerSession("conv-1");
    expect(bindLink("conv-1", "tok-unknown")).toBe(true);
    vi.mocked(getArtifactByToken).mockResolvedValue(null);

    const res = await GET(blobReq("tok-unknown"), routeCtx);
    expect(res.status).toBe(404);
  });

  it("a token never bound to the session is 410 even when the row exists", async () => {
    // The converse control. The token resolves in the store, but it was never
    // bound to this live session, so it is a dead link - not an unknown token.
    registerSession("conv-1");
    expect(bindLink("conv-1", "tok-1")).toBe(true);
    // "tok-2" is not bound to conv-1, though getArtifactByToken would find it.

    const res = await GET(blobReq("tok-2"), routeCtx);
    expect(res.status).toBe(410);
    expect(((await res.json()) as { error: string }).error).toBe("session_expired");
  });

  it("a token with no live session is refused before the store is consulted", async () => {
    // Non-vacuity control: prove 410 is reached by the SESSION check, not by
    // the store happening to miss. Bind the token under conv-2 (live) but
    // request it under conv-1 (never registered): still 410, and getArtifact-
    // ByToken is not consulted, so the refusal cannot be the store's doing.
    registerSession("conv-2", "client-a");
    expect(bindLink("conv-2", "tok-1")).toBe(true);
    vi.mocked(getArtifactByToken).mockClear();

    const res = await GET(blobReq("tok-1"), routeCtx); // conv-1, unregistered
    expect(res.status).toBe(410);
    expect(vi.mocked(getArtifactByToken)).not.toHaveBeenCalled();
  });
});