import './globals.css';
import { ReactNode } from 'react';
import { Geist, Geist_Mono, Instrument_Serif } from 'next/font/google';
import { DashboardProvider } from '@/lib/dashboard-context';
import { AppShellProvider } from '@/components/app-shell-context';
import { ThemeProvider } from '@/components/theme-provider';
import AppFrame from '@/components/app-frame';
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

// Editorial display serif — the digiquant.io house headline face. Self-hosted by
// next/font so it satisfies the Olympus CSP (font-src 'self' data:).
const instrumentSerif = Instrument_Serif({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-instrument-serif',
  display: 'swap',
});

export const metadata = {
  title: 'Olympus — DigiQuant',
  description: 'DigiQuant Olympus — AI-orchestrated investment intelligence (Atlas research + Hermes analysis & PM)',
  icons: {
    icon: '/olympus/favicon.svg',
    shortcut: '/olympus/favicon.svg',
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={instrumentSerif.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className={`qn-blueprint-bg accent-digiquant min-h-screen bg-bg-primary text-text-primary antialiased ${geistSans.variable} ${geistMono.variable} ${instrumentSerif.variable}`}>
        <ThemeProvider>
          <MotionLayer />
          <DashboardProvider>
            <AppShellProvider>
              <AppFrame>{children}</AppFrame>
            </AppShellProvider>
          </DashboardProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
