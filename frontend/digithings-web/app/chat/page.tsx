import type { Metadata } from "next";
import { DtNav } from "@/components/DtNav";
import { ChatEmbedShell } from "@/components/ChatEmbedShell";
import { embedOriginForChat } from "@/lib/security-headers.mjs";

export const metadata: Metadata = {
  title: "digichat — the digithings assistant",
  description:
    "Ask digichat anything about the digithings architecture — grounded via digigraph " +
    "and digivault, running on digillm. No sign-up.",
};

/** Same origin as CSP frame-src (default https://digithings.ai for Containers). */
const EMBED_ORIGIN = embedOriginForChat();

/**
 * /chat — DtNav + iframe to digichat /embed (digigraph backend).
 * Same Container as /chat/occ; tenant via host=digithings.ai.
 */
export default function ChatPage() {
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
        <ChatEmbedShell embedOrigin={EMBED_ORIGIN} />
      </main>
    </>
  );
}
