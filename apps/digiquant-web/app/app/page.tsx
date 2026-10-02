import type { Metadata } from "next";
import { DeskPage } from "@/components/desk/desk-page";

export const metadata: Metadata = {
  title: "Terminal — digiquant",
  description: "The digiquant terminal. Each block is one read of the official dashboard API.",
};

export default function TerminalHome() {
  return (
    <main id="main" className="h-[100svh]">
      <DeskPage path="/brief" />
    </main>
  );
}
