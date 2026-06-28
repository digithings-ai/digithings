import type { Metadata } from "next";
import { DigiNav } from "@/components/landing/DigiNav";
import { DigiChatSession } from "@/components/DigiChatSession";

export const metadata: Metadata = {
  title: "DigiChat — the DigiThings assistant",
  description:
    "Ask DigiChat anything about the DigiThings architecture — grounded in the DigiVault docs, " +
    "running on a free model pool. No sign-up.",
};

// The /chat route is the full-screen signature DigiChat experience. The marketing
// that used to live here (hero + canned transcript + feature cards) now streams as
// the bot's own self-introduction inside DigiChatSession — the chat IS the pitch.
export default function ChatPage() {
  return (
    <>
      <DigiNav />
      <main className="dc-page">
        <DigiChatSession />
      </main>
    </>
  );
}
