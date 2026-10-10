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
 * Authentication runs FIRST, ahead of the session check, for two reasons. The
 * gate is the same `requireDigiChatAuth` every DigiChat route uses, so an OCC
 * embed's invite key is honoured here exactly as it is on the list endpoint;
 * and answering `session_expired` to a caller who never passed the gate would
 * report link lifetime to a request that is not entitled to ask about it.
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