/**
 * `/api/conversations/[id]/artifacts/blob` - the link target a chat reply
 * hands to the browser, and the only place artifact link lifetime is enforced.
 *
 * `serveArtifact` in the sibling route answers `404 not_found` when a token
 * does not resolve. That answer is correct for a token the store cannot find,
 * but it is wrong for a token that used to work: after a reload or a new
 * session the row is still in the database and still owned by the caller, so
 * the honest answer is that the *link* died, not that the *artifact* is
 * missing. A user who reloads must see "this link expired", not a 404 that
 * reads like the file never existed.
 *
 * So the session check runs here, before the store is consulted, and it is a
 * distinct state: `410 Gone` with `error: "session_expired"`.
 *
 * Authentication runs FIRST, ahead of the session check, so answering
 * `session_expired` never reports link lifetime to a request that is not
 * entitled to ask about it. That ordering is what this route exists for, and
 * it is preserved: a dead link still answers 401, never 410, for a caller
 * that never passed the gate.
 *
 * **Which callers the gate admits.** `requireDigiChatAuth` reads the
 * `authorization` header (a `digi_live_…` machine key) and the OIDC session
 * cookie, and never reads `x-embed-token`. A tenant configured
 * `auth: anonymous` - the OCC embed in `occ-embed.yaml` is one - gets 401
 * here, and that is the intended answer rather than a gap: it holds no
 * credential for this surface. The invite key is honoured on `/api/chat` and
 * `/api/embed/tenant-config`, which resolve the tenant through
 * `resolveVerifiedEmbedTenant`, not here. An earlier version of this comment
 * claimed the OCC invite key was honoured "exactly as it is on the list
 * endpoint"; that was false (DIG-3241), and the comparison was also
 * self-referential, since the list endpoint runs this same gate and reads
 * these same two credentials. See the sibling route's comment for why
 * admitting an embed caller is not a one-line change.
 *
 * `serveArtifact` re-checks the gate after the handoff; the second call is
 * idempotent and keeps that function honest for its other caller.
 *
 * Lifetime has no TTL by decision (DIG-2638): links die on reload or session
 * end. `isLiveSessionLink` is true only for a link bound to a session that is
 * still registered, and `registerSession` retires a client's previous session
 * when a new id arrives for the same client key - that is the reload rule.
 */
import { isLiveSessionLink } from "@/lib/session-links";
import { requireDigiChatAuth } from "@/lib/request-auth";
import { serveArtifact } from "../route";

type RouteContext = { params: Promise<{ id: string }> };

/**
 * A link the session no longer owns. 410 rather than 404 because the resource
 * is gone in the sense the user cares about - the link - while the artifact
 * row may well still exist. `Cache-Control: no-store` keeps a browser from
 * holding on to the expired state across a reload.
 */
function sessionExpired() {
  return Response.json(
    {
      error: "session_expired",
      message:
        "This artifact link belongs to a chat session that has ended. Open /artifacts in the current chat to list this session's files.",
    },
    { status: 410, headers: { "cache-control": "no-store, private" } }
  );
}

export async function GET(req: Request, ctx: RouteContext) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;

  const token =
    new URL(req.url).searchParams.get("token")?.trim() ?? "";
  if (!token) return Response.json({ error: "invalid_body" }, { status: 400 });

  // The session id IS the conversation id (session-links.ts), and the
  // conversation id is already in the path. Taking it from there rather than
  // from a query parameter means a caller cannot name a session it does not
  // own: there is exactly one candidate and the store re-checks ownership
  // downstream anyway.
  const { id: conversationId } = await ctx.params;
  if (!isLiveSessionLink(conversationId, token)) return sessionExpired();

  return serveArtifact(req, { ...ctx, token });
}