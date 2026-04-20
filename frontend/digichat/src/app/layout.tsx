import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { auth } from "@/auth";
import { Providers } from "@/components/providers";

const inter = Inter({
  variable: "--font-sans",
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
    <html lang="en" className={`${inter.variable} dark h-full antialiased`}>
      <body className="accent-digichat flex min-h-full flex-col bg-background font-sans text-foreground">
        <Providers session={session} localBootstrapEnabled={localBootstrapEnabled}>
          <div className="flex min-h-dvh w-full flex-1 flex-col">{children}</div>
        </Providers>
      </body>
    </html>
  );
}
