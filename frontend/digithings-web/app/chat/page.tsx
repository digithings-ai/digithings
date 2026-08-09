import type { Metadata } from "next";
import { DtNav } from "@/components/DtNav";
import { ChatEmbedShell } from "@/components/ChatEmbedShell";

export const metadata: Metadata = {
  title: "digichat — the digithings assistant",
  description:
    "Ask digichat anything about the digithings architecture — grounded via digigraph " +
    "and digivault, running on digillm. No sign-up.",
};

const EMBED_ORIGIN = process.env.NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN?.trim() ?? "";

/**
 * /chat — DtNav + iframe to digichat /embed (digigraph backend).
 * Set NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN to the digichat Node public URL
 * (Cloudflare Tunnel). See infra/digichat-digithings/README.md.
 */
export default function ChatPage() {
  return (
    <>
      <DtNav />
      <main>
        {EMBED_ORIGIN ? (
          <ChatEmbedShell embedOrigin={EMBED_ORIGIN} />
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
