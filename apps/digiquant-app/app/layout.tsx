import './globals.css';
import type { ReactNode } from 'react';
import { Geist_Mono, Inter, JetBrains_Mono } from 'next/font/google';
import { Shell } from '@/components/Shell';

export const metadata = { title: 'digiquant' };

// Same pairing as the canvas mock: Inter for prose, JetBrains Mono for chrome and figures.
const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });
const mono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-jbmono', display: 'swap' });
// The digiquant.io wordmark is Geist Mono; it is used for the brand only.
const brand = Geist_Mono({ subsets: ['latin'], variable: '--font-geist-mono', display: 'swap' });

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable} ${brand.variable}`}>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
