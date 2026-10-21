import { requireDigiChatAuth } from "@/lib/request-auth";
import { loadReplayStyles } from "@digithings/ui/replay/assets";

/** Chat CSS and fonts for a browser export when the page cannot read its sheets. */
export async function GET(req: Request) {
  const authCtx = await requireDigiChatAuth(req);
  if (authCtx instanceof Response) return authCtx;
  return new Response(loadReplayStyles(), {
    status: 200,
    headers: {
      "content-type": "text/css; charset=utf-8",
      "cache-control": "private, max-age=3600",
      "x-content-type-options": "nosniff",
    },
  });
}
