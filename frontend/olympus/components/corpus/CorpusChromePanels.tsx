'use client';

import Link from 'next/link';
import {
  CORPUS_KEY_KINDS,
  HOUSE_PROFILE_PIN,
  TYPED_CHROME_GAP_COPY,
} from '@/lib/house-chrome';
import type { CorpusSectionId } from './CorpusSectionNav';

function GapNote({ children }: { children: string }) {
  return (
    <p
      data-testid="typed-chrome-gap"
      className="border border-hair bg-term-bg px-4 py-3 font-mono text-[0.72rem] leading-relaxed text-ink-mute"
    >
      {children}
    </p>
  );
}

export function CorpusIdentityPanel() {
  return (
    <section data-testid="corpus-identity" className="space-y-4">
      <header className="space-y-1">
        <h2 className="font-display text-2xl font-normal tracking-tight text-ink">
          Shared research corpus
        </h2>
        <p className="text-sm text-ink-soft">
          Tenant-agnostic pins only — keys are <code className="font-mono text-ink">theme:</code>,{' '}
          <code className="font-mono text-ink">asset:</code>, or{' '}
          <code className="font-mono text-ink">segment:</code>. House writes defaults; overlays
          publish-if-missing. Portfolio holdings never belong here.
        </p>
      </header>
      <ul className="flex flex-wrap gap-2" aria-label="Corpus key kinds">
        {CORPUS_KEY_KINDS.map((kind) => (
          <li
            key={kind}
            className="rounded-md border border-hair bg-surface px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-ink-soft"
          >
            {kind}:
          </li>
        ))}
      </ul>
      <GapNote>{TYPED_CHROME_GAP_COPY.corpus_service_role_only}</GapNote>
    </section>
  );
}

export function BookChromePanel() {
  return (
    <section data-testid="book-chrome" className="space-y-4">
      <header className="space-y-1">
        <h2 className="font-display text-2xl font-normal tracking-tight text-ink">
          digithings house book
        </h2>
        <p className="text-sm text-ink-soft">
          The ETF house book is the digithings-owned always-on baseline. Inspect holdings, tearsheet,
          ledger, and period status on Portfolio — this chrome does not fork a private research book.
        </p>
      </header>
      <div className="flex flex-wrap gap-3">
        <Link
          href="/portfolio"
          className="rounded-lg border border-accent/40 bg-accent/15 px-4 py-2 text-sm font-medium text-accent"
        >
          Open holdings book
        </Link>
        <Link
          href="/portfolio/ledger"
          className="rounded-lg border border-hair px-4 py-2 text-sm font-medium text-ink-soft hover:text-ink"
        >
          Open ledger
        </Link>
        <Link
          href="/portfolio/period"
          className="rounded-lg border border-hair px-4 py-2 text-sm font-medium text-ink-soft hover:text-ink"
        >
          Open periods
        </Link>
      </div>
    </section>
  );
}

export function ProfilePinsPanel() {
  return (
    <section data-testid="profile-pins" className="space-y-4">
      <header className="space-y-1">
        <h2 className="font-display text-2xl font-normal tracking-tight text-ink">
          House profile pins
        </h2>
        <p className="text-sm text-ink-soft">
          Read-only. Overlays cannot cancel or replace the house run. Editing profiles is out of
          scope for this chrome.
        </p>
      </header>
      <dl
        data-testid="house-profile-pin"
        className="grid gap-3 border border-hair bg-surface p-4 font-mono text-[0.78rem] sm:grid-cols-2"
      >
        <div>
          <dt className="text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">profile_key</dt>
          <dd className="mt-1 text-ink">{HOUSE_PROFILE_PIN.profileKey}</dd>
        </div>
        <div>
          <dt className="text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">label</dt>
          <dd className="mt-1 text-ink">{HOUSE_PROFILE_PIN.label}</dd>
        </div>
        <div>
          <dt className="text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">schema_version</dt>
          <dd className="mt-1 text-ink">{HOUSE_PROFILE_PIN.schemaVersion}</dd>
        </div>
        <div>
          <dt className="text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">version_id</dt>
          <dd className="mt-1 break-all text-ink-soft">{HOUSE_PROFILE_PIN.versionId}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">house default</dt>
          <dd className="mt-1 text-ink">{HOUSE_PROFILE_PIN.isHouseDefault ? 'yes — always-on' : 'no'}</dd>
        </div>
      </dl>
      <GapNote>{TYPED_CHROME_GAP_COPY.profile_live_read_blocked}</GapNote>
    </section>
  );
}

export function CorpusChromeBody({ tab }: { tab: CorpusSectionId }) {
  if (tab === 'book') return <BookChromePanel />;
  if (tab === 'profile') return <ProfilePinsPanel />;
  return <CorpusIdentityPanel />;
}
