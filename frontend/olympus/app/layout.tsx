import './globals.css';
import { ReactNode } from 'react';
import type { Metadata } from 'next';
import { Geist, Geist_Mono, Fraunces } from 'next/font/google';
import { AuthProvider } from '@/lib/auth-context';
import { AuthGate } from '@/lib/auth-gate';
import { ThemeProvider } from '@/components/theme-provider';
import MotionLayer from '@/components/motion-layer';

/** Default + invalid keys → follow prefers-color-scheme; light/dark fixed; auto → OS */
const THEME_INIT = `(function(){try{var t=localStorage.getItem('olympus-theme')||localStorage.getItem('dt-theme');var d=document.documentElement;d.classList.remove('light','dark');var dark;if(t==='light')dark=false;else if(t==='dark')dark=true;else{dark=window.matchMedia('(prefers-color-scheme: dark)').matches;}var m=dark?'dark':'light';d.classList.add(m);d.setAttribute('data-theme',m);}catch(e){document.documentElement.classList.add('dark');document.documentElement.setAttribute('data-theme','dark');}})();`;

// Self-hosted at build time by next/font (served from /olympus/_next/static/media),
// so they satisfy the Olympus CSP (font-src 'self' data:) — no fonts.googleapis.com.
const geistSans = Geist({
  subsets: ['latin'],
  variable: '--font-geist-sans',
  display: 'swap',
});

const geistMono = Geist_Mono({
  subsets: ['latin'],
  variable: '--font-geist-mono',
  display: 'swap',
});

// Editorial display serif — the digiquant.io house headline face (Fraunces).
// Self-hosted by next/font so it satisfies the Olympus CSP (font-src 'self' data:).
const fraunces = Fraunces({
  subsets: ['latin'],
  variable: '--font-fraunces',
  display: 'swap',
});

export const metadata: Metadata = {
  metadataBase: new URL('https://digiquant.io'),
  applicationName: 'Olympus',
  title: 'Olympus — digiquant',
  description: 'digiquant Olympus — AI-orchestrated investment intelligence (Atlas research + Hermes analysis & PM)',
  manifest: '/olympus/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    title: 'Olympus',
    statusBarStyle: 'black-translucent',
  },
  icons: {
    icon: [
      { url: '/olympus/icons/olympus-app-dark.svg', type: 'image/svg+xml', media: '(prefers-color-scheme: dark)' },
      { url: '/olympus/icons/olympus-app-light.svg', type: 'image/svg+xml', media: '(prefers-color-scheme: light)' },
      { url: '/olympus/icons/olympus-app-32.png', type: 'image/png', sizes: '32x32' },
    ],
    shortcut: '/olympus/icons/olympus-app-32.png',
    apple: [
      { url: '/olympus/icons/olympus-app-touch-dark.png', type: 'image/png', sizes: '180x180', media: '(prefers-color-scheme: dark)' },
      { url: '/olympus/icons/olympus-app-touch-light.png', type: 'image/png', sizes: '180x180', media: '(prefers-color-scheme: light)' },
    ],
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      // Font variables must live on <html>: globals.css re-declares --font-sans/--font-mono
      // on :root via var(--font-geist-*), which resolves at the declaring element — variables
      // scoped to <body> are invisible there and the tokens go invalid app-wide (#1538).
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className="qn-blueprint-bg min-h-screen bg-bg text-ink antialiased">
        <ThemeProvider>
          <MotionLayer />
          <AuthProvider>
            <AuthGate>{children}</AuthGate>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
