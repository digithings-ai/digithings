/**
 * DigiThings DigiChat — Worker fronting a Cloudflare Container.
 * Proxies /embed, DigiChat APIs, and /_dtchat assets to the DigiChat Node image.
 */
import { Container, getContainer } from "@cloudflare/containers";

export class DigiChatContainer extends Container {
  defaultPort = 3000;
  /** Keep warm enough for chat; tune cost vs cold-start. */
  sleepAfter = "10m";
}

export interface Env {
  DIGICHAT: DurableObjectNamespace<DigiChatContainer>;
}

/** Paths DigiChat owns on digithings.ai (Pages owns /chat and the rest). */
function shouldProxyToDigiChat(pathname: string): boolean {
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

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (!shouldProxyToDigiChat(url.pathname)) {
      return new Response(
        "DigiChat Worker: path not routed. Use Pages for marketing routes.",
        { status: 404 },
      );
    }
    // Single shared instance for ungated digithings chat (stateless digivault).
    const container = getContainer(env.DIGICHAT, "digithings");
    return container.fetch(request);
  },
};
