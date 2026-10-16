/**
 * GET /healthz — auth-exempt liveness probe, always `{"ok": true}`.
 *
 * Stack convention (root AGENTS.md § Liveness vs status): load balancers and
 * orchestrator restart policy key on this route, which never depends on
 * license state. A probe that must decide "may this deployment serve turns?"
 * reads `license_status` off `GET /api/health` instead. This route
 * deliberately never consults license state.
 */

export async function GET() {
  return Response.json({ ok: true }, { status: 200 });
}
