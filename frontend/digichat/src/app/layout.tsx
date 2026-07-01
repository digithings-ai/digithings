import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { auth } from "@/auth";
import { Providers } from "@/components/providers";

// Unified with the rest of the stack (self-hosted by next/font → CSP-safe).
const geistSans = Geist({
  variable: "--font-sans",
  subsets: ["latin"],
});
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DigiChat · digithings",
  description: "Production chat UI for the DigiGraph orchestrator.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const session = await auth();
  const localBootstrapEnabled =
    process.env.NODE_ENV !== "production" &&
    !!process.env.DIGICHAT_LOCAL_AUTH_KEY?.trim();
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} dark h-full antialiased`}>
      <body className="accent-digichat flex min-h-full flex-col bg-background font-sans text-foreground">
        <Providers session={session} localBootstrapEnabled={localBootstrapEnabled}>
          <div className="flex min-h-dvh w-full flex-1 flex-col">{children}</div>
        </Providers>
      </body>
    </html>
  );
}
