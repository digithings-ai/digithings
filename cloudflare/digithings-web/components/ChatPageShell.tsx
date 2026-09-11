import { DtNav } from "@/components/DtNav";
import { ChatEmbedShell } from "@/components/ChatEmbedShell";

/**
 * Shared full-viewport chat shell for /chat and /chat/occ: hover-autohide
 * nav plus the digichat iframe. The routes differ only in metadata and the
 * embed tenant host.
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
      <DtNav autoHide="hover" />
      <main
        id="main"
        tabIndex={-1}
        className="dc-chat-main"
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100dvh",
          // No inline paddingTop here on desktop: DtNav is `autoHide="hover"`
          // — fixed-position and hidden by default, so it overlays on reveal
          // rather than reserving space. Reserving --dq-nav-h anyway would
          // leave a permanent gap at the top even while the bar is hidden.
          // Touch/narrow viewports are a different story — nav-shell.css
          // forces the bar to stay visible there, so `.dc-chat-main`
          // (globals.css) reserves --nav-shell-h under that same media query.
          boxSizing: "border-box",
        }}
      >
        <ChatEmbedShell embedOrigin={embedOrigin} embedHost={embedHost} />
      </main>
    </>
  );
}
