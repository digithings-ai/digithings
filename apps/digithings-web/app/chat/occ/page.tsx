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
 *
 * Invite link (DIG-1210): `https://digithings.ai/chat/occ?token=<key>`. The key
 * is forwarded verbatim to the embed as `?token=`, which is the parameter
 * digichat already enforces per tenant (`X-Embed-Token`).
 *
 * This route only *accepts* the key. As of this commit OCC is still on
 * digichat's first-party allowlist, so the tenant authorizes it without one —
 * the link is plumbed and ready, and it starts to matter the moment OCC leaves
 * that allowlist (the follow-up PR, which is deliberately a separate deploy
 * because it would otherwise take the live chat down with it).
 */
export default function OccChatPage() {
  return (
    <ChatPageShell
      embedOrigin={EMBED_ORIGIN}
      embedHost={OCC_CHAT_EMBED_HOST}
      acceptsInviteToken
    />
  );
}
