import './globals.css';
import type { ReactNode } from 'react';
import { Shell } from '@/components/Shell';

export const metadata = { title: 'digiquant' };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
