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

/** Same origin as CSP `frame-src` (env or https://digichat.digithings.ai). */
const EMBED_ORIGIN = embedOriginForChat();

/**
 * /chat/occ — DtNav + iframe to digichat /embed with virtual host occ.digithings.ai.
 * Same digichat Node as /chat; tenant slug `occ` + occ_help corpus.
 * See docs/projects/online-compliance-center/README.md.
 */
export default function OccChatPage() {
  return (
    <>
      <DtNav />
      <main>
        <ChatEmbedShell
          embedOrigin={EMBED_ORIGIN}
          embedHost={OCC_CHAT_EMBED_HOST}
        />
      </main>
    </>
  );
}
