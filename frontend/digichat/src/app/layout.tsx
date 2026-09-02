import type { Metadata } from "next";
import { Geist_Mono } from "next/font/google";
import "./globals.css";
import { themeInitScript } from "@digithings/web";
import { auth } from "@/auth";
import { Providers } from "@/components/providers";

// Unified with the rest of the stack (self-hosted by next/font → CSP-safe).
// Utilitarian v0.1: one Geist Mono face for claim, body, and chrome.
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "digichat · digithings",
  description: "Production chat UI for the digigraph orchestrator.",
};

// Pre-paint companion to the shared themeInitScript: mirror [data-theme] onto
// the .dark/.light classes, because the Tailwind `dark:` variant
// (@custom-variant in globals.css) and the /embed wrapper key off classes.
// Runtime flips are mirrored by ThemeClassSync in providers.tsx — same rule,
// keep the two in lockstep.
const themeClassSyncScript =
  "try{var e=document.documentElement,l=e.getAttribute('data-theme')==='light';e.classList.toggle('light',l);e.classList.toggle('dark',!l)}catch(t){}";

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const session = await auth();
  const localBootstrapEnabled =
    process.env.NODE_ENV !== "production" &&
    !!process.env.DIGICHAT_LOCAL_AUTH_KEY?.trim();
  // data-theme="dark" + className "dark" are the SSR/no-JS defaults (matches
  // the pre-canon hardcoded dark shell); themeInitScript re-points both
  // pre-paint from dt-theme / prefers-color-scheme. suppressHydrationWarning:
  // those scripts legitimately flip this element's attributes before React
  // hydrates — scoped to <html>'s own attributes only.
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={`${geistMono.variable} dark h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <script dangerouslySetInnerHTML={{ __html: themeClassSyncScript }} />
      </head>
      <body className="accent-digichat flex min-h-full flex-col bg-background font-mono text-foreground">
        <Providers session={session} localBootstrapEnabled={localBootstrapEnabled}>
          <div className="flex min-h-dvh w-full flex-1 flex-col">{children}</div>
        </Providers>
      </body>
    </html>
  );
}
