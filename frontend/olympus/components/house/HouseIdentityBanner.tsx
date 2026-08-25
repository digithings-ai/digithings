'use client';

import Link from 'next/link';
import { HOUSE_BOOK_IDENTITY } from '@/lib/house-identity';

/**
 * Compact house-book identity strip for Brief / Portfolio entry surfaces.
 * Links into Corpus | Book | Profile chrome at /house.
 */
export default function HouseIdentityBanner() {
  return (
    <div
      data-testid="house-identity-banner"
      className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-hair bg-term-bg/40 px-5 py-2.5 sm:px-7"
    >
      <div className="min-w-0">
        <p className="font-mono text-[10px] uppercase tracking-widest text-ink-mute">
          {HOUSE_BOOK_IDENTITY.owner} · {HOUSE_BOOK_IDENTITY.label}
        </p>
        <p className="truncate text-[11px] text-ink-soft">{HOUSE_BOOK_IDENTITY.cadence}</p>
      </div>
      <Link
        href="/house?tab=corpus"
        className="shrink-0 text-[10px] font-medium text-accent hover:underline"
      >
        Corpus · Book · Profile →
      </Link>
    </div>
  );
}
