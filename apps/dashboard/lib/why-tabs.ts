import type { ElementType } from 'react';
import { BookOpen, MessagesSquare } from 'lucide-react';

export type WhyTabId = 'read' | 'deliberations';

export interface WhyTab {
  id: WhyTabId;
  label: string;
  icon: ElementType<{ size?: number }>;
}

/** Why, ordered synthesized → argued. */
export const WHY_TABS: WhyTab[] = [
  { id: 'read', label: 'The read', icon: BookOpen },
  { id: 'deliberations', label: 'Deliberations', icon: MessagesSquare },
];

/**
 * Resolve the active Why tab from URL params. An explicit `why` wins; otherwise
 * the default is The read.
 *
 * The standalone Documents archive was retired (deferred behind distinct-dates>1).
 * Legacy research/library deep links (`tab`/`date`/`docKey`) are now handled by the
 * /research and /library redirects, which forward to the Pipeline node grammar — so
 * they never reach this resolver.
 */
export function resolveWhyTab(params: { why?: string | null }): WhyTabId {
  const why = (params.why || '').toLowerCase();
  if (why === 'read' || why === 'deliberations') return why;
  return 'read';
}
