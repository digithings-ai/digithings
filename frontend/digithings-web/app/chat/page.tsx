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
      <DtNav />
      <main
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100dvh",
          paddingTop: "var(--dq-nav-h)",
          boxSizing: "border-box",
        }}
      >
        <ChatEmbedShell embedOrigin={EMBED_ORIGIN} />
      </main>
    </>
  );
}
