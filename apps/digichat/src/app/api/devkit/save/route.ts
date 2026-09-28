import { isLocalBaselinePreview } from "@/lib/baseline-preview";
import { resolveDevkitConfigDir, saveDevkitEntry } from "@/lib/devkit-save";

export const dynamic = "force-dynamic";

/** Hardening bound on save bodies (loopback dev-only already; 413 past it). */
const MAX_SAVE_BYTES = 1_000_000;

/**
 * Dev-only devkit surface (no `requireDigiChatAuth()` — same documented
 * exception as dev-only `POST /api/baseline-chat`): writes one entry's
 * draft text back to its YAML file. 404 outside development loopback.
 * Writes `<config>/<rel>` verbatim (minus sentinel restore) plus a
 * `<rel>.bak` backup; env tenants are never writable.
 */
export async function POST(req: Request) {
  if (!isLocalBaselinePreview(req)) {
    return new Response(null, { status: 404 });
  }
  const declared = req.headers.get("content-length");
  if (declared !== null && Number(declared) > MAX_SAVE_BYTES) {
    return Response.json({ ok: false, issues: ["(body): exceeds 1 MB"] }, { status: 413 });
  }
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ ok: false, issues: ["(body): expected JSON"] }, { status: 400 });
  }
  const input = body as { id?: unknown; text?: unknown };
  if (typeof input.id !== "string" || typeof input.text !== "string") {
    return Response.json(
      { ok: false, issues: ["(body): expected { id: string, text: string }"] },
      { status: 400 },
    );
  }
  if (input.text.length > MAX_SAVE_BYTES) {
    return Response.json({ ok: false, issues: ["(body): exceeds 1 MB"] }, { status: 413 });
  }
  const result = saveDevkitEntry(resolveDevkitConfigDir(), {
    id: input.id,
    text: input.text,
  });
  return Response.json(result, { status: result.ok ? 200 : 422 });
}
