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
 * The edge gate (Worker route plus the Pages function) serves this shell only
 * when the invite token or the occ_invite cookie is valid. OCC is not on the
 * first-party allowlist, so a request that reaches the embed without the key
 * answers 404.
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
