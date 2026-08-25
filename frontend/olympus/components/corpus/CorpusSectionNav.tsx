'use client';

import Link from 'next/link';
import { Library, BookMarked, UserRound } from 'lucide-react';
import { SubpageStickyTabBar, subpageTabButtonClass } from '@/components/subpage-tab-bar';

export type CorpusSectionId = 'corpus' | 'book' | 'profile';

const SECTIONS: {
  id: CorpusSectionId;
  label: string;
  href: string;
  icon: typeof Library;
}[] = [
  { id: 'corpus', label: 'Corpus', href: '/corpus', icon: Library },
  { id: 'book', label: 'Book', href: '/corpus?tab=book', icon: BookMarked },
  { id: 'profile', label: 'Profile', href: '/corpus?tab=profile', icon: UserRound },
];

export default function CorpusSectionNav({ active }: { active: CorpusSectionId }) {
  return (
    <SubpageStickyTabBar aria-label="Corpus book profile">
      {SECTIONS.map(({ id, label, href, icon: Icon }) => (
        <Link key={id} href={href} scroll={false} className={subpageTabButtonClass(active === id)}>
          <Icon size={16} />
          {label}
        </Link>
      ))}
    </SubpageStickyTabBar>
  );
}
