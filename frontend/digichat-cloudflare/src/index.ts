/**
 * digithings digichat — Worker fronting one Cloudflare Container.
 * Proxies /embed, digichat APIs, and /_dtchat assets to the digichat Node image.
 *
 * Website paths (different chats, same Container):
 *   digithings.ai/chat      → Pages iframe → /embed?host=digithings.ai
 *   digithings.ai/chat/occ  → Pages iframe → /embed?host=occ.digithings.ai
 */
import { Container, getContainer } from "@cloudflare/containers";
import {
  SHARED_DIGICHAT_CONTAINER_ID,
  shouldProxyToDigiChat,
} from "./paths";

export class DigiChatContainer extends Container {
  defaultPort = 3000;
  /** Keep warm enough for chat; tune cost vs cold-start. */
  sleepAfter = "15m";
}

export interface Env {
  DIGICHAT: DurableObjectNamespace<DigiChatContainer>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (!shouldProxyToDigiChat(url.pathname)) {
      return new Response(
        "digichat Worker: path not routed. Marketing /chat shells are on Pages.",
        { status: 404 },
      );
    }
    // One shared instance — digithings, OCC, and future tenants via embed registry.
    const container = getContainer(env.DIGICHAT, SHARED_DIGICHAT_CONTAINER_ID);
    return container.fetch(request);
  },
};
