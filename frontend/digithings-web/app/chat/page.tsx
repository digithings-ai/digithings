import type { Metadata } from "next";
import { DtNav } from "@/components/DtNav";
import { ChatEmbedShell } from "@/components/ChatEmbedShell";

export const metadata: Metadata = {
  title: "digichat — the digithings assistant",
  description:
    "Ask digichat anything about the digithings architecture — grounded in the digivault docs, " +
    "running on a free model pool. No sign-up.",
};

/** /chat — DtNav outside; digichat /embed iframe fills the content pane (Phase 3). */
export default function ChatPage() {
  return (
    <>
      <DtNav />
      <ChatEmbedShell />
    </>
  );
}
