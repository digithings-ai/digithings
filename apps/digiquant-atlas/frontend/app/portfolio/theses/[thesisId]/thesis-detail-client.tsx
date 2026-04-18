'use client';

import { useParams } from 'next/navigation';
import ThesisDetailPageInner from '@/components/portfolio/theses/ThesisDetailPageInner';

/** `key` remounts the detail view when the route segment changes so thesis history state stays in sync. */
export default function ThesisDetailClient() {
  const params = useParams();
  const rawId = typeof params?.thesisId === 'string' ? params.thesisId : '';
  const thesisId = rawId ? decodeURIComponent(rawId) : '';
  return <ThesisDetailPageInner key={thesisId} thesisId={thesisId} />;
}
