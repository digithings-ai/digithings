import { ChatEmbedShell } from "@/components/ChatEmbedShell";

/**
 * Shared full-viewport chat shell for /chat: the digichat iframe alone, with no
 * site top bar (Chris, 2026-10-13: chat fills the page). /chat/occ no longer
 * uses it — that path is the app itself, behind the Worker's invite gate
 * (2026-10-27 consolidation), so the invite-key plumbing it needed is gone.
 */
export function ChatPageShell({
  embedOrigin,
  embedHost,
}: {
  embedOrigin: string;
  embedHost?: string;
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
        <ChatEmbedShell embedOrigin={embedOrigin} embedHost={embedHost} />
      </main>
    </>
  );
}
