'use client';

import Link from 'next/link';
import { Layers, BookMarked, Scale, TrendingUp } from 'lucide-react';
import { SubpageStickyTabBar, subpageTabButtonClass } from '@/components/subpage-tab-bar';

export type PortfolioSectionId = 'holdings' | 'theses' | 'performance' | 'attribution';

const SECTIONS: {
  id: PortfolioSectionId;
  label: string;
  href: string;
  icon: typeof Layers;
}[] = [
  { id: 'holdings', label: 'Holdings', href: '/portfolio', icon: Layers },
  { id: 'theses', label: 'Theses', href: '/portfolio?tab=theses', icon: BookMarked },
  { id: 'performance', label: 'Performance', href: '/portfolio/performance', icon: TrendingUp },
  { id: 'attribution', label: 'Attribution', href: '/portfolio/attribution', icon: Scale },
];

export default function PortfolioSectionNav({ active }: { active: PortfolioSectionId }) {
  return (
    <SubpageStickyTabBar aria-label="Portfolio sections">
      {SECTIONS.map(({ id, label, href, icon: Icon }) => (
        <Link key={id} href={href} scroll={false} className={subpageTabButtonClass(active === id)}>
          <Icon size={16} />
          {label}
        </Link>
      ))}
    </SubpageStickyTabBar>
  );
}
