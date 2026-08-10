/**
 * Paths digichat owns on digithings.ai (Pages owns /chat and marketing).
 * digithings + OCC (and future tenants) share one Container — tenant selection
 * is via /embed?host=… / X-Embed-Host, not separate Container instances.
 */
export function shouldProxyToDigiChat(pathname: string): boolean {
  return (
    pathname === "/embed" ||
    pathname.startsWith("/embed/") ||
    pathname === "/api/chat" ||
    pathname.startsWith("/api/chat/") ||
    pathname.startsWith("/api/embed/") ||
    pathname.startsWith("/api/byok/") ||
    pathname === "/api/health" ||
    pathname.startsWith("/_dtchat/")
  );
}

/** Single Durable Object / Container name for all marketing tenants. */
export const SHARED_DIGICHAT_CONTAINER_ID = "shared";
