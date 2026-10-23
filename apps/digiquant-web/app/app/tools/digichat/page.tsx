import type { Metadata } from "next";
import { ChatPane } from "@/components/desk/desk-chat";

export const metadata: Metadata = {
  title: "digichat — digiquant",
  description: "Financial digichat. Sessions follow the active desk and the official dashboard API.",
};

export default function ToolsDigichatPage() {
  return <ChatPane />;
}
