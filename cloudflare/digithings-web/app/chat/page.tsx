import type { Metadata } from "next";
import { ChatPageShell } from "@/components/ChatPageShell";
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
  return <ChatPageShell embedOrigin={EMBED_ORIGIN} />;
}
