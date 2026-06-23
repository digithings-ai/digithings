import type { ElementType } from 'react';
import { BookOpen, MessagesSquare, FolderOpen } from 'lucide-react';

export type WhyTabId = 'read' | 'deliberations' | 'documents';

export interface WhyTab {
  id: WhyTabId;
  label: string;
  icon: ElementType<{ size?: number }>;
}

/** Why, ordered synthesized → argued → sourced. */
export const WHY_TABS: WhyTab[] = [
  { id: 'read', label: 'The read', icon: BookOpen },
  { id: 'deliberations', label: 'Deliberations', icon: MessagesSquare },
  { id: 'documents', label: 'Documents', icon: FolderOpen },
];

/**
 * Resolve the active Why tab from URL params. An explicit `why` wins; otherwise
 * legacy research/library deep-link params (`tab`/`date`/`docKey`, preserved by
 * the /research and /library redirects) land on Documents; the default is The read.
 */
export function resolveWhyTab(params: {
  why?: string | null;
  tab?: string | null;
  date?: string | null;
  docKey?: string | null;
}): WhyTabId {
  const why = (params.why || '').toLowerCase();
  if (why === 'read' || why === 'deliberations' || why === 'documents') return why;
  if (params.tab || params.date || params.docKey) return 'documents';
  return 'read';
}
