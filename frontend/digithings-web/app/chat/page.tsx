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

/** Same origin as CSP `frame-src` (env or https://digichat.digithings.ai). */
const EMBED_ORIGIN = embedOriginForChat();

/**
 * /chat — DtNav + iframe to digichat /embed (digigraph backend).
 * Origin defaults to digichat.digithings.ai; override with
 * NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN for staging tunnels.
 * See infra/digichat-digithings/README.md.
 */
export default function ChatPage() {
  return (
    <>
      <DtNav />
      <main>
        <ChatEmbedShell embedOrigin={EMBED_ORIGIN} />
      </main>
    </>
  );
}
