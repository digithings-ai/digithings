import type { Metadata } from "next";
import { DtNav } from "@/components/DtNav";
import {
  ChatEmbedShell,
  OCC_CHAT_EMBED_HOST,
} from "@/components/ChatEmbedShell";
import { embedOriginForChat } from "@/lib/security-headers.mjs";

export const metadata: Metadata = {
  title: "OCC help assistant — digichat",
  description:
    "Ask about Online Compliance Center policies, procedures, and help articles — " +
    "grounded on the OCC help corpus via digigraph. No sign-up.",
};

/** Same origin as CSP frame-src (default https://digithings.ai for Containers). */
const EMBED_ORIGIN = embedOriginForChat();

/**
 * /chat/occ — same digichat Container as /chat; tenant via host=occ.digithings.ai.
 */
export default function OccChatPage() {
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
        <ChatEmbedShell
          embedOrigin={EMBED_ORIGIN}
          embedHost={OCC_CHAT_EMBED_HOST}
        />
      </main>
    </>
  );
}
