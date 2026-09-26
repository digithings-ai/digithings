import { isLocalBaselinePreview } from "@/lib/baseline-preview";
import { validateDevkitObject, validateDevkitText } from "@/lib/devkit-configs";

export const dynamic = "force-dynamic";

/**
 * Dev-only devkit surface (no `requireDigiChatAuth()` — same documented
 * exception as dev-only `POST /api/baseline-chat`): validates draft config
 * text/objects against the deploy-config schema for the editor and (P1) save.
 * 404 outside development loopback. Never echoes secrets — callers submit
 * redacted drafts holding `__DEVKIT_PRESERVED__` sentinels. Note: a sentinel
 * passes plain-string fields but fails url-refined ones (`gate.consumeUrl`
 * must be https), so an untouched redacted draft can report issues there;
 * P1 save restores sentinels from disk before its final validation.
 */
export async function POST(req: Request) {
  if (!isLocalBaselinePreview(req)) {
    return new Response(null, { status: 404 });
  }
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ ok: false, issues: ["(body): expected JSON"] }, { status: 400 });
  }
  const input = body as { text?: unknown; object?: unknown };
  if (typeof input.text === "string") {
    return Response.json(validateDevkitText(input.text));
  }
  if (input.object !== undefined) {
    return Response.json(validateDevkitObject(input.object));
  }
  return Response.json(
    { ok: false, issues: ["(body): expected { text: string } or { object: unknown }"] },
    { status: 400 },
  );
}
