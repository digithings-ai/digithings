/**
 * A deterministic stand-in for the digichat API, so a recorded frame never
 * depends on a live backend (DIG-2698, ADR D7: recorded frames, not live
 * sockets).
 *
 * The exporter points the client at this server through DIGI_CHAT_URL
 * (packages/surface-config/src/endpoints.ts:42-47). The client resolves its
 * API base when its module is evaluated (src/app.tsx:46), so the URL must be
 * in the environment before the client module loads — src/capture.tsx sets it
 * from the URL this server reports, then imports the app.
 *
 * The server binds an ephemeral port (`packages/tui-frame/src/fixture-server.ts`),
 * so a second exporter never collides with the first.
 *
 * The payloads are the shapes the client reads (src/read.ts:8-11,99,189): a
 * conversation list and one conversation's messages. Any other route answers
 * 404, so a frame can never be recorded from an unexpected endpoint.
 */

import {
  startFixtureApi as startServer,
  type FixtureApi,
} from "../../../packages/tui-frame/src/fixture-server.ts";

const CONVERSATIONS = {
  conversations: [
    { id: "s1", title: "book" },
    { id: "s2", title: "desk" },
  ],
};

const MESSAGES = {
  messages: [
    { id: "u1", role: "user", text: "what is a recorded frame" },
    {
      id: "a1",
      role: "assistant",
      text: "a recorded captureCharFrame() frame, rendered as text",
    },
  ],
};

export type { FixtureApi };

/** Start the fixture API on a free loopback port. */
export function startFixtureApi(options?: { unref?: boolean }): Promise<FixtureApi> {
  return startServer({
    unref: options?.unref,
    route: (pathname) => {
      if (pathname === "/api/conversations") {
        return { status: 200, body: CONVERSATIONS };
      }
      if (pathname.startsWith("/api/conversations/")) {
        return { status: 200, body: MESSAGES };
      }
      return {
        status: 404,
        body: { error: { code: "not_found", message: `unknown route ${pathname}` } },
      };
    },
  });
}
