/** Edge-only paths that do not proxy to Langfuse Web. */
export function isEdgeOnlyPath(pathname: string): boolean {
  return (
    pathname === "/_langfuse/healthz" ||
    pathname === "/_langfuse/worker-wake"
  );
}

/** Stable Durable Object ids — one Web replica set + one Worker replica. */
export const LANGFUSE_WEB_CONTAINER_ID = "digitrace-langfuse-web";
export const LANGFUSE_WORKER_CONTAINER_ID = "digitrace-langfuse-worker";
