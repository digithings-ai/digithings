import { ChatEmbedShell } from "@/components/ChatEmbedShell";

/**
 * Shared full-viewport chat shell for /chat and /chat/occ: the digichat
 * iframe alone, with no site top bar (Chris, 2026-10-13: chat fills the page). The routes differ only in metadata and the
 * embed tenant host.
 */
export function ChatPageShell({
  embedOrigin,
  embedHost,
  acceptsInviteToken,
}: {
  embedOrigin: string;
  embedHost?: string;
  /** Forward the invite key off this route's URL to digichat (DIG-1210). */
  acceptsInviteToken?: boolean;
}) {
  return (
    <>
      <main
        id="main"
        tabIndex={-1}
        className="dc-chat-main"
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100dvh",
          boxSizing: "border-box",
        }}
      >
        <ChatEmbedShell
          embedOrigin={embedOrigin}
          embedHost={embedHost}
          acceptsInviteToken={acceptsInviteToken}
        />
      </main>
    </>
  );
}
