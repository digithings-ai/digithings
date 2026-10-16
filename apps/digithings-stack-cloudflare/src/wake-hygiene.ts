/**
 * Wake hygiene (cost): requests that must never boot the paid stack Container.
 *
 * Every Container wake bills the boot plus the whole `sleepAfter` tail
 * (~5 min). Traced 2026-10-13: the stack was woken all night by liveness
 * probes (an hourly `digithings.ai/api/health` check whose digichat health
 * handler in turn pings `graph.digithings.ai/health`) and by internet
 * scanners (`/.env`, `/.git/config`, `*.php`). None of them needs the
 * Container, so the Worker answers them itself:
 *
 * - Scanner paths: a plain 404 at the edge.
 * - `/health` and `/healthz`: proxied to the Container only while it is
 *   already running (a deep check costs nothing then); while it sleeps the
 *   Worker answers 200 `{"status":"ok","container":"sleeping"}`. A cold
 *   Container wakes on the first real request, which is the supported path.
 */

const SCANNER_PATH =
  /^\/(?:\.env|\.git|\.aws|\.ssh|\.svn|\.ds_store|wp-|wordpress|phpmyadmin|server-info|server-status|cgi-bin|actuator|vendor\/phpunit)|\.(?:php\d?|asp|aspx|jsp|cgi|env|bak|sql)$/i;

const HEALTH_PATHS = new Set(["/health", "/healthz"]);

export function isScannerPath(pathname: string): boolean {
  return SCANNER_PATH.test(pathname);
}

export function isHealthProbe(request: Request, pathname: string): boolean {
  return (request.method === "GET" || request.method === "HEAD") && HEALTH_PATHS.has(pathname);
}

/** Container statuses in which a deep health proxy will not cause a boot. */
export function containerIsAwake(status: string | undefined): boolean {
  return status === "running" || status === "healthy";
}

export function sleepingHealthResponse(request: Request): Response {
  const body = JSON.stringify({
    status: "ok",
    service: "digithings-stack",
    container: "sleeping",
    note: "Worker up; the container is asleep and wakes on the first real request.",
  });
  return new Response(request.method === "HEAD" ? null : body, {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export function scannerResponse(): Response {
  return new Response("not found", { status: 404 });
}
