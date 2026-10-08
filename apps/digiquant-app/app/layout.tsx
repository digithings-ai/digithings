import './globals.css';
import '../styles/pipeline.css';
import '../styles/markets.css';
import '../styles/desk.css';
import type { ReactNode } from 'react';
import { AccessProvider } from '@/components/Access';
import { Shell } from '@/components/Shell';
import { fontVariables } from './fonts';

export const metadata = { title: 'digiquant' };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={fontVariables}>
      <body>
        <AccessProvider>
          <Shell>{children}</Shell>
        </AccessProvider>
      </body>
    </html>
  );
}
