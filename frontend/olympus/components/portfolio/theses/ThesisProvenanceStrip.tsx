'use client';

import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { buildPipelineHref, stageForDocumentKey } from '@/lib/pipeline-links';

export function ThesisProvenanceStrip({
  date,
  documentKey,
}: {
  date: string | null;
  documentKey: string;
}) {
  if (!date) return null;
  const stage = stageForDocumentKey(documentKey);
  const href = buildPipelineHref({ date, stage, node: documentKey });
  return (
    <section className="flex flex-wrap items-center gap-2 border-t border-border-subtle pt-4 text-sm">
      <span className="text-text-muted">Provenance</span>
      <span className="font-mono text-xs text-text-secondary">{date}</span>
      <Link href={href} className="ml-auto inline-flex items-center gap-1 text-accent hover:underline">
        Open the pipeline day
        <ArrowUpRight size={14} aria-hidden />
      </Link>
    </section>
  );
}
