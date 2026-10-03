import { Geist_Mono } from "next/font/google";

/**
 * The first-party digichat skin reads `--font-geist-mono`
 * (`packages/ui/src/styles/chat-aui.css`). The marketing page's mono is
 * JetBrains, so the chat frame has to load the same face digichat loads.
 */
export const digichatFont = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
});
