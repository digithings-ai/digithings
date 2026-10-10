/**
 * `/api/conversations/[id]/artifacts/blob` - the download link an oversized
 * retrieval hands to the model.
 *
 * Two gates stand in front of the bytes and both are checked here, not left to
 * the caller:
 *
 *   - `isLiveSessionLink` (`session-links.ts`) - this link was minted by *this*
 *     live session. A reload that re-registers under a new session id, or an
 *     `endSession`, stops it validating at once. There is no TTL, so nothing
 *     else can keep it alive.
 *   - `serveArtifact` - which re-checks conversation ownership in Postgres
 *     before it reads a byte, and answers `not_found` when the check fails.
 *
 * `serveArtifact` is exported from the sibling route rather than reimplemented
 * here so the ownership check, the content headers and the byte read cannot
 * drift apart between the listing path and the download path.
 *
 * A link that reaches a later session is refused even with a valid invite key.
 * That is the decision on DIG-2638: the link belongs to the session that made
 * it, not to whoever holds the credential.
 */
import { serveArtifact } from "@/app/api/conversations/[id]/artifacts/route";
import { isLiveSessionLink } from "@/lib/session-links";

type RouteContext = { params: Promise<{ id: string }> };

export async function GET(req: Request, ctx: RouteContext) {
  const { id: conversationId } = await ctx.params;
  const token = new URL(req.url).searchParams.get("token")?.trim();
  if (!token) return Response.json({ error: "invalid_body" }, { status: 400 });
  // A link that was never bound to a live session reads the same as one that
  // was retired: both are simply not there. Never say which.
  if (!isLiveSessionLink(conversationId, token)) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  return serveArtifact(req, { params: ctx.params, token });
}
