'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { Lock } from 'lucide-react';
import { useCanAccessProduct } from '@/lib/use-entitlement';
import { isOlympusAuthEnabled } from '@/lib/supabase';

/**
 * Gate a custom Olympus client product (FX Hub now; future products reuse this).
 * Presentation only — data plane must still deny via RLS / dedicated project keys.
 */
export function ClientProductGate({
  productKey,
  children,
  title = 'Client product',
  body = 'This surface is available to allowlisted client emails. Contact the operator if you expected access.',
}: {
  productKey: string;
  children: ReactNode;
  title?: string;
  body?: string;
}) {
  const allowed = useCanAccessProduct(productKey);
  if (!isOlympusAuthEnabled() || allowed) {
    return <>{children}</>;
  }
  return (
    <section
      data-testid="client-product-locked"
      data-product-key={productKey}
      className="m-6 border border-hair bg-term-bg/50 px-4 py-5"
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center border border-accent/30 bg-accent/10 text-accent"
          aria-hidden
        >
          <Lock size={14} />
        </span>
        <div className="min-w-0 space-y-2">
          <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
            {title}
          </p>
          <p className="text-sm text-ink-soft">{body}</p>
          <Link
            href="/settings#billing"
            className="inline-flex items-center text-sm font-medium text-accent transition-colors hover:underline"
          >
            Settings → Billing
          </Link>
        </div>
      </div>
    </section>
  );
}
