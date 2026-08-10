import type { Metadata } from "next";
import { DtNav } from "@/components/DtNav";
import {
  ChatEmbedShell,
  OCC_CHAT_EMBED_HOST,
} from "@/components/ChatEmbedShell";
import { resolveDigichatEmbedOrigin } from "@/lib/security-headers.mjs";

export const metadata: Metadata = {
  title: "OCC help assistant — digichat",
  description:
    "Ask about Online Compliance Center policies, procedures, and help articles — " +
    "grounded on the OCC help corpus via digigraph. No sign-up.",
};

/** Same resolver as CSP `frame-src` (see lib/security-headers.mjs + prebuild). */
const EMBED_ORIGIN = resolveDigichatEmbedOrigin() ?? "";

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
        {EMBED_ORIGIN ? (
          <ChatEmbedShell
            embedOrigin={EMBED_ORIGIN}
            embedHost={OCC_CHAT_EMBED_HOST}
          />
        ) : (
          <p className="dc-page" style={{ padding: "2rem", maxWidth: "36rem" }}>
            digichat is not configured for this build. Set{" "}
            <code>NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN</code> to the digichat Node
            URL (digigraph stack). See{" "}
            <code>infra/digichat-digithings/README.md</code>.
          </p>
        )}
      </main>
    </>
  );
}
