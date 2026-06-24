'use client';

import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';

export default function SystemPage() {
  return (
    <div className={`${SUBPAGE_MAX} space-y-8 py-4 md:py-6`}>
      <header className="space-y-2">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">
          System
        </p>
        <h1 className="font-display text-3xl tracking-tight text-text-primary sm:text-4xl">
          How Olympus works
        </h1>
        <p className="max-w-3xl text-sm leading-relaxed text-text-secondary">
          Is it running, is it healthy, what does it cost, and how does it work?
        </p>
      </header>
      {/* Zone 1 — Live status (Tasks 3–6) */}
      {/* Zone 2 — How it works (Tasks 7–8) */}
    </div>
  );
}
