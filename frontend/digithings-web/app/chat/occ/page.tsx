import type { Metadata } from "next";
import { ChatPageShell } from "@/components/ChatPageShell";
import { OCC_CHAT_EMBED_HOST } from "@/components/ChatEmbedShell";
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
  return <ChatPageShell embedOrigin={EMBED_ORIGIN} embedHost={OCC_CHAT_EMBED_HOST} />;
}
