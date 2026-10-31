import type { Metadata } from "next";
import { Cabin, Geist_Mono, IBM_Plex_Mono, Inter, Mulish } from "next/font/google";
import "./globals.css";
import { faviconThemeScript, themeInitScript } from "@digithings/ui";
import { p } from "@/lib/base-path";
import { PUBLIC_ORIGIN } from "@/lib/public-origin";
import { auth } from "@/auth";
import { Providers } from "@/components/providers";
import {
  getDigichatConfig,
  getPrimaryDeployment,
} from "@/lib/deploy-config/loader";

/** Catalog skins stay Inter / IBM Plex. `--font-geist-mono` is for `chrome.skin: digichat` only. */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-ibm-plex-mono",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
});

/**
 * Tenant fonts (src/lib/tenant-fonts.ts TENANT_FONTS). Self-hosted by
 * next/font, so CSP `font-src 'self'` holds. preload: false — only a tenant
 * page whose fonts name the face makes the browser fetch it.
 */
const brandCabin = Cabin({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-brand-cabin",
  preload: false,
});

const brandMulish = Mulish({
  subsets: ["latin"],
  variable: "--font-brand-mulish",
  preload: false,
});

const faviconInit = faviconThemeScript({
  dark: p("/icons/digi-app-dark.svg"),
  light: p("/icons/digi-app-light.svg"),
  touchDark: p("/icons/digi-app-touch-dark.png"),
  touchLight: p("/icons/digi-app-touch-light.png"),
});

export const metadata: Metadata = {
  // Absolute og:image / twitter:image (see lib/public-origin.ts).
  metadataBase: PUBLIC_ORIGIN,
  title: "digichat · digithings",
  description: "Production chat UI for the digigraph orchestrator.",
  icons: {
    icon: [
      { url: "/icons/digi-app-dark.svg", type: "image/svg+xml" },
      { url: "/favicon.ico", sizes: "48x48" },
    ],
    apple: [{ url: "/icons/digi-app-touch-dark.png", sizes: "180x180" }],
  },
  openGraph: {
    title: "digichat · digithings",
    description: "Production chat UI for the digigraph orchestrator.",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "digithings" }],
  },
  twitter: {
    card: "summary_large_image",
    images: ["/og.png"],
  },
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
      className={`${inter.variable} ${ibmPlexMono.variable} ${geistMono.variable} ${brandCabin.variable} ${brandMulish.variable} ${theme === "light" ? "light" : "dark"} h-full antialiased`}
    >
      {/* Pre-paint theme: plain inline <head> scripts, like digithings.ai.
          next/script "beforeInteractive" in the App Router does not run
          inline: it queues the body into self.__next_s and the Next runtime
          runs it only after its chunks load. Until then the page painted
          the server default (data-theme="dark", no palette), and the boot
          loader and the chat could each paint a different theme. These run
          before <body> parses, so a saved dt-theme / dt-palette (shared with
          digithings.ai, same origin) or the OS scheme holds from the first
          frame. The embed route's own pin scripts run later, in <body>. */}
      <head>
        <script id="digichat-theme-init" dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <script id="digichat-favicon-theme" dangerouslySetInnerHTML={{ __html: faviconInit }} />
        <script
          id="digichat-theme-class-sync"
          dangerouslySetInnerHTML={{ __html: themeClassSyncScript }}
        />
      </head>
      <body
        className={`${inter.className} accent-digichat flex min-h-full flex-col bg-background text-foreground`}
      >
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
