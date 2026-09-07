import type { Metadata } from "next";
import Script from "next/script";
import { IBM_Plex_Mono, Inter } from "next/font/google";
import "./globals.css";
import { themeInitScript } from "@digithings/web";
import { auth } from "@/auth";
import { Providers } from "@/components/providers";
import {
  getDigichatConfig,
  getPrimaryDeployment,
} from "@/lib/deploy-config/loader";

/** Stock product fonts — match (vanilla) Inter / IBM Plex Mono, not Geist CLI. */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-ibm-plex-mono",
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

function deployChromeTheme(): "dark" | "light" {
  try {
    return getPrimaryDeployment(getDigichatConfig())?.chrome.theme === "light"
      ? "light"
      : "dark";
  } catch {
    return "dark";
  }
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const session = await auth();
  const localBootstrapEnabled =
    process.env.NODE_ENV !== "production" &&
    !!process.env.DIGICHAT_LOCAL_AUTH_KEY?.trim();
  const theme = deployChromeTheme();
  // data-theme + className are the SSR/no-JS defaults from chrome.theme;
  // themeInitScript may re-point from dt-theme / prefers-color-scheme.
  // suppressHydrationWarning: those scripts legitimately flip this element's
  // attributes before React hydrates — scoped to <html>'s own attributes only.
  return (
    <html
      lang="en"
      data-theme={theme}
      suppressHydrationWarning
      className={`${inter.variable} ${ibmPlexMono.variable} ${theme === "light" ? "light" : "dark"} h-full antialiased`}
    >
      <body
        className={`${inter.className} accent-digichat flex min-h-full flex-col bg-background text-foreground`}
      >
        <Script
          id="digichat-theme-init"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: themeInitScript }}
        />
        <Script
          id="digichat-theme-class-sync"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: themeClassSyncScript }}
        />
        <Providers
          session={session}
          localBootstrapEnabled={localBootstrapEnabled}
        >
          <div className="flex min-h-dvh w-full flex-1 flex-col">{children}</div>
        </Providers>
      </body>
    </html>
  );
}
