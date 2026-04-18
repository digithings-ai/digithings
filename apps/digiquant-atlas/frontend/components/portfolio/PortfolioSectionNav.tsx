'use client';

import Link from 'next/link';
import { Activity, Brain, BookMarked, Layers, TrendingUp } from 'lucide-react';
import { SubpageStickyTabBar, subpageTabButtonClass } from '@/components/subpage-tab-bar';

export type PortfolioSectionId = 'allocations' | 'activity' | 'performance' | 'analysis' | 'theses';

const SECTIONS: {
  id: PortfolioSectionId;
  label: string;
  href: string;
  icon: typeof Layers;
}[] = [
  { id: 'allocations', label: 'Allocations', href: '/portfolio', icon: Layers },
  { id: 'activity', label: 'Activity', href: '/portfolio?tab=activity', icon: Activity },
  { id: 'performance', label: 'Performance', href: '/portfolio?tab=performance', icon: TrendingUp },
  { id: 'analysis', label: 'Intelligence', href: '/portfolio?tab=analysis', icon: Brain },
  { id: 'theses', label: 'Theses', href: '/portfolio/theses', icon: BookMarked },
];

export default function PortfolioSectionNav({ active }: { active: PortfolioSectionId }) {
  return (
    <SubpageStickyTabBar aria-label="Portfolio sections">
      {SECTIONS.map(({ id, label, href, icon: Icon }) => (
        <Link
          key={id}
          href={href}
          scroll={false}
          className={subpageTabButtonClass(active === id)}
        >
          <Icon size={16} />
          {label}
        </Link>
      ))}
    </SubpageStickyTabBar>
  );
}
