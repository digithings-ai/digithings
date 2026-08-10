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
        <ChatEmbedShell
          embedOrigin={EMBED_ORIGIN}
          embedHost={OCC_CHAT_EMBED_HOST}
        />
      </main>
    </>
  );
}
