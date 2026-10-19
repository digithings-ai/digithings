import type { Env } from "./env";

export type StartRun = (env: Env, instanceId: string) => Promise<void>;

function authorized(request: Request, secret: string): boolean {
  const header = request.headers.get("Authorization") ?? "";
  const expected = `Bearer ${secret}`;
  if (header.length !== expected.length) return false;
  let mismatch = 0;
  for (let index = 0; index < header.length; index += 1) {
    mismatch |= header.charCodeAt(index) ^ expected.charCodeAt(index);
  }
  return mismatch === 0;
}

function normalizePath(pathname: string): string {
  if (pathname.length > 1 && pathname.endsWith("/")) return pathname.slice(0, -1);
  return pathname || "/";
}

export async function handleFetch(request: Request, env: Env, start: StartRun): Promise<Response> {
  const path = normalizePath(new URL(request.url).pathname);
  if (request.method === "GET" && (path === "/" || path === "/healthz")) {
    return Response.json({ ok: true, service: "corpus-index", dry_run: env.DRY_RUN === "1" });
  }
  if (request.method === "POST" && path === "/run") {
    if (!env.CRON_KICK_SECRET) return new Response("Not Found", { status: 404 });
    if (!authorized(request, env.CRON_KICK_SECRET)) {
      return new Response("Unauthorized", { status: 401 });
    }
    await start(env, `manual-${Date.now()}`);
    return Response.json({ ok: true, started: true });
  }
  return new Response("Not Found", { status: 404 });
}
