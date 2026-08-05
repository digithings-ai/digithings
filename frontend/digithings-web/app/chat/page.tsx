import type { Metadata } from "next";
import { DtNav } from "@/components/DtNav";
import { DigiChatSession } from "@/components/DigiChatSession";

export const metadata: Metadata = {
  title: "digichat — the digithings assistant",
  description:
    "Ask digichat anything about the digithings architecture — grounded in the digivault docs, " +
    "running on a free model pool. No sign-up.",
};

/**
 * /chat — full-screen DigiChat via shared digichat-ui + Pages Function digivault
 * backend (free Cloudflare plan; no Containers / iframe).
 */
export default function ChatPage() {
  return (
    <>
      <DtNav />
      <main className="dc-page">
        <DigiChatSession />
      </main>
    </>
  );
}
