'use client';

import Link from 'next/link';
import { BookMarked, Library, UserRound } from 'lucide-react';
import { SubpageStickyTabBar, subpageTabButtonClass } from '@/components/subpage-tab-bar';
import {
  HOUSE_BOOK_IDENTITY,
  HOUSE_CHROME_TABS,
  type HouseChromeTabId,
} from '@/lib/house-identity';

const ICONS = {
  corpus: Library,
  book: BookMarked,
  profile: UserRound,
} as const;

export default function HouseIdentityChrome({ active }: { active: HouseChromeTabId }) {
  return (
    <div data-testid="house-identity-chrome">
      <div className="border-b border-hair bg-surface/80 px-5 py-2.5 sm:px-7">
        <p className="font-mono text-[10px] uppercase tracking-widest text-ink-mute">
          {HOUSE_BOOK_IDENTITY.owner} · {HOUSE_BOOK_IDENTITY.label}
        </p>
        <p className="mt-0.5 text-xs text-ink-soft">{HOUSE_BOOK_IDENTITY.cadence}</p>
      </div>
      <SubpageStickyTabBar aria-label="Corpus Book Profile">
        {HOUSE_CHROME_TABS.map(({ id, label, href }) => {
          const Icon = ICONS[id];
          return (
            <Link key={id} href={href} scroll={false} className={subpageTabButtonClass(active === id)}>
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </SubpageStickyTabBar>
    </div>
  );
}
