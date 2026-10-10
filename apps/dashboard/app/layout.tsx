import './globals.css';
import { ReactNode } from 'react';
import type { Metadata } from 'next';
import { AuthProvider } from '@/lib/auth-context';
import { AuthGate } from '@/lib/auth-gate';
import { ThemeProvider } from '@/components/theme-provider';
import MotionLayer from '@/components/motion-layer';
import { fontVariables } from './fonts';

/** Default + invalid keys → follow prefers-color-scheme; light/dark fixed; auto → OS */
const THEME_INIT = `(function(){try{var t=localStorage.getItem('dashboard-theme')||localStorage.getItem('dashboard-theme')||localStorage.getItem('dt-theme');var d=document.documentElement;d.classList.remove('light','dark');var dark;if(t==='light')dark=false;else if(t==='dark')dark=true;else{dark=window.matchMedia('(prefers-color-scheme: dark)').matches;}var m=dark?'dark':'light';d.classList.add(m);d.setAttribute('data-theme',m);}catch(e){document.documentElement.classList.add('dark');document.documentElement.setAttribute('data-theme','dark');}})();`;

export const metadata: Metadata = {
  metadataBase: new URL('https://digiquant.io'),
  applicationName: 'digiquant',
  title: 'digiquant',
  description: 'digiquant — AI-orchestrated investment intelligence (research + portfolio)',
  manifest: '/dashboard/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    title: 'digiquant',
    statusBarStyle: 'black-translucent',
  },
  icons: {
    icon: [
      { url: '/dashboard/icons/dashboard-app-dark.svg', type: 'image/svg+xml', media: '(prefers-color-scheme: dark)' },
      { url: '/dashboard/icons/dashboard-app-light.svg', type: 'image/svg+xml', media: '(prefers-color-scheme: light)' },
      { url: '/dashboard/icons/dashboard-app-32.png', type: 'image/png', sizes: '32x32' },
    ],
    shortcut: '/dashboard/icons/dashboard-app-32.png',
    apple: [
      { url: '/dashboard/icons/dashboard-app-touch-dark.png', type: 'image/png', sizes: '180x180', media: '(prefers-color-scheme: dark)' },
      { url: '/dashboard/icons/dashboard-app-touch-light.png', type: 'image/png', sizes: '180x180', media: '(prefers-color-scheme: light)' },
    ],
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      // Font variables must live on <html>: globals.css re-declares --font-sans/--font-mono/--font-display
      // on :root via the token stacks, which resolve at the declaring element — variables
      // scoped to <body> are invisible there and the tokens go invalid app-wide (#1538).
      className={fontVariables}
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
