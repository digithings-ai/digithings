import './globals.css';
import { ReactNode, Suspense } from 'react';
import { Geist, Geist_Mono } from 'next/font/google';
import { DashboardProvider } from '@/lib/dashboard-context';
import { AppShellProvider } from '@/components/app-shell-context';
import { ThemeProvider } from '@/components/theme-provider';
import Sidebar from '@/components/sidebar';
import MobileAppBar from '@/components/mobile-app-bar';
import CommandPalette from '@/components/command-palette';
import MotionLayer from '@/components/motion-layer';

/** Default + invalid keys → follow prefers-color-scheme; light/dark fixed; auto → OS */
const THEME_INIT = `(function(){try{var t=localStorage.getItem('olympus-theme')||localStorage.getItem('dt-theme');var d=document.documentElement;d.classList.remove('light','dark');var dark;if(t==='light')dark=false;else if(t==='dark')dark=true;else{dark=window.matchMedia('(prefers-color-scheme: dark)').matches;}d.classList.add(dark?'dark':'light');}catch(e){document.documentElement.classList.add('dark');}})();`;

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
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className={`qn-blueprint-bg accent-digiquant min-h-screen bg-bg-primary text-text-primary antialiased ${geistSans.variable} ${geistMono.variable}`}>
        <ThemeProvider>
          <MotionLayer />
          <DashboardProvider>
            <AppShellProvider>
              <div className="flex min-h-screen">
                <Suspense fallback={<aside className="w-[260px] shrink-0 border-r border-border-subtle bg-bg-glass" />}>
                  <Sidebar />
                </Suspense>
                <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto max-h-screen">
                  <div className="qn-page-chrome">
                    <div className="qn-crumbs">
                      <strong>Olympus</strong>
                      <span aria-hidden="true"> / </span>
                      <span>investment intelligence</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <a href="https://digiquant.io" target="_blank" rel="noopener noreferrer">
                        Open digiquant.io -&gt;
                      </a>
                      <span className="qn-env">
                        {process.env.NEXT_PUBLIC_OLYMPUS_VERSION ?? 'v0.1 · dev'}
                      </span>
                    </div>
                  </div>
                  <MobileAppBar />
                  <CommandPalette />
                  <div className="flex min-h-0 flex-1 flex-col">{children}</div>
                </main>
              </div>
            </AppShellProvider>
          </DashboardProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
