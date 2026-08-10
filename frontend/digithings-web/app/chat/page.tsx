import type { Metadata } from "next";
import { DtNav } from "@/components/DtNav";
import { ChatEmbedShell } from "@/components/ChatEmbedShell";
import { DigiChatSession } from "@/components/DigiChatSession";
import { resolveDigichatEmbedOrigin } from "@/lib/security-headers.mjs";

export const metadata: Metadata = {
  title: "digichat — the digithings assistant",
  description:
    "Ask digichat anything about the digithings architecture — grounded via digigraph " +
    "and digivault, running on digillm. No sign-up.",
};

/** Same resolver as CSP `frame-src` (see lib/security-headers.mjs + prebuild). */
const EMBED_ORIGIN = resolveDigichatEmbedOrigin() ?? "";

/**
 * /chat — prefer digichat Node iframe when `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` is
 * set (dogfood cutover: digichat → digigraph). Until Tunnel + Pages env are
 * live, fall back to DigiChatSession + Pages Function `/api/chat` so the
 * public site stays usable (#2068).
 *
 * See `infra/digichat-digithings/README.md`.
 */
export default function ChatPage() {
  return (
    <>
      <DtNav />
      <main className={EMBED_ORIGIN ? undefined : "dc-page"}>
        {EMBED_ORIGIN ? (
          <ChatEmbedShell embedOrigin={EMBED_ORIGIN} />
        ) : (
          <DigiChatSession />
        )}
      </main>
    </>
  );
}
