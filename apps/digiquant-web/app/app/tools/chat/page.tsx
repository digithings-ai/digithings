import type { Metadata } from "next";
import { ChatPane } from "@/components/desk/desk-chat";

export const metadata: Metadata = {
  title: "digichat — digiquant",
  description: "digichat. Sessions and messages come from the official dashboard API.",
};

export default function ToolsChatPage() {
  return <ChatPane />;
}
