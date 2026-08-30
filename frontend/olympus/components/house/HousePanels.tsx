'use client';

import Link from 'next/link';
import {
  CORPUS_KEY_PREFIXES,
  HOUSE_BOOK_IDENTITY,
  HOUSE_PROFILE_PINS,
  isSharedCorpusKey,
} from '@/lib/house-identity';

export function CorpusPanel({ sampleKeys }: { sampleKeys: string[] }) {
  const shared = sampleKeys.filter(isSharedCorpusKey).slice(0, 12);
  return (
    <section data-testid="house-corpus-panel" className="space-y-4">
      <div>
        <h1 className="font-display text-xl font-normal tracking-tight text-ink">Shared corpus</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-soft">{HOUSE_BOOK_IDENTITY.summary}</p>
      </div>
      <div className="border border-hair bg-term-bg/40 px-4 py-3">
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Tenant-agnostic keys
        </p>
        <ul className="mt-2 flex flex-wrap gap-2 font-mono text-xs text-ink">
          {CORPUS_KEY_PREFIXES.map((prefix) => (
            <li key={prefix} className="rounded border border-hair bg-surface px-2 py-1">
              {prefix}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-ink-mute">
          Profile identity never appears in the key. digithings owns the always-on house run;
          profiles publish-if-missing into this shared store.
        </p>
      </div>
      {shared.length > 0 ? (
        <div>
          <p className="mb-2 text-[10px] font-medium uppercase tracking-widest text-ink-mute">
            Sample keys from loaded docs
          </p>
          <ul className="divide-y divide-hair/60 border border-hair">
            {shared.map((key) => (
              <li key={key} className="px-3 py-2 font-mono text-xs text-ink-soft">
                {key}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-ink-mute">
          No <code className="font-mono text-[11px]">theme:</code> /{' '}
          <code className="font-mono text-[11px]">asset:</code> /{' '}
          <code className="font-mono text-[11px]">segment:</code> keys in the current dashboard
          snapshot — contract still applies when Track B corpus rows land.
        </p>
      )}
    </section>
  );
}

export function BookPanel() {
  return (
    <section data-testid="house-book-panel" className="space-y-4">
      <div>
        <h1 className="font-display text-xl font-normal tracking-tight text-ink">House book</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-soft">
          {HOUSE_BOOK_IDENTITY.label} — inspect holdings, tearsheet, and ledger activity on Portfolio.
        </p>
      </div>
      <ul className="space-y-2 text-sm">
        <li>
          <Link href="/portfolio" className="text-accent hover:underline">
            Holdings →
          </Link>
        </li>
        <li>
          <Link href="/portfolio/performance" className="text-accent hover:underline">
            Tearsheet →
          </Link>
        </li>
        <li>
          <Link href="/portfolio/ledger" className="text-accent hover:underline">
            Ledger →
          </Link>
        </li>
      </ul>
    </section>
  );
}

export function ProfilePanel() {
  return (
    <section data-testid="house-profile-panel" className="space-y-4">
      <div>
        <h1 className="font-display text-xl font-normal tracking-tight text-ink">
          House profile pins
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-soft">{HOUSE_PROFILE_PINS.note}</p>
      </div>
      <dl className="grid gap-3 border border-hair bg-term-bg/40 px-4 py-3 sm:grid-cols-2">
        <div>
          <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Profile id</dt>
          <dd className="font-mono text-sm text-ink">{HOUSE_PROFILE_PINS.profileId}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Editable</dt>
          <dd className="text-sm text-ink">{HOUSE_PROFILE_PINS.editable ? 'yes' : 'read-only'}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Universe</dt>
          <dd className="text-sm text-ink">{HOUSE_PROFILE_PINS.universe}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Risk</dt>
          <dd className="text-sm text-ink">{HOUSE_PROFILE_PINS.riskStance}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-[10px] uppercase tracking-widest text-ink-mute">Themes</dt>
          <dd className="text-sm text-ink">{HOUSE_PROFILE_PINS.themes}</dd>
        </div>
      </dl>
    </section>
  );
}
