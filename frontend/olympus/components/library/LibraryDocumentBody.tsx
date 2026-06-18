'use client';

import type { LibraryDocumentView } from '@/lib/queries';
import { normalizeMarkdownFirstHeadingDate } from '@/lib/render-document-from-payload';
import { SafeMarkdown } from '@/components/SafeMarkdown';
import RebalanceDocumentView from './RebalanceDocumentView';
import DeltaRequestDocumentView from './DeltaRequestDocumentView';
import DeliberationDocumentView from './DeliberationDocumentView';
import DigestDocumentView from './DigestDocumentView';
import EvolutionSourcesDocumentView from './EvolutionSourcesDocumentView';
import OpportunityScreenerDocumentView from './OpportunityScreenerDocumentView';
import GenericDiffDocumentView from './GenericDiffDocumentView';
import AnalystDocumentView from './AnalystDocumentView';

export default function LibraryDocumentBody({
  view,
  markdown,
  payload,
  documentKey,
  docDate,
}: {
  view: LibraryDocumentView;
  markdown: string;
  payload: Record<string, unknown> | null;
  documentKey: string;
  docDate: string;
}) {
  const isDigest = (documentKey || '').toLowerCase() === 'digest';
  const normalizedMarkdown = normalizeMarkdownFirstHeadingDate(markdown, docDate);

  if (view === 'markdown' && isDigest && docDate) {
    return <DigestDocumentView key={docDate} docDate={docDate} fallbackMarkdown={normalizedMarkdown} />;
  }

  switch (view) {
    case 'rebalance':
      return <RebalanceDocumentView payload={payload} fallbackMarkdown={normalizedMarkdown} />;
    case 'delta_request':
      return <DeltaRequestDocumentView payload={payload} />;
    case 'deliberation':
    case 'risk_debate':
      // `risk_debate` reuses DeliberationDocumentView which now renders the
      // aggressive/conservative/key-tension shape alongside the bull/bear debate.
      return <DeliberationDocumentView payload={payload} fallbackMarkdown={normalizedMarkdown} />;
    case 'analyst':
      return <AnalystDocumentView payload={payload} fallbackMarkdown={normalizedMarkdown} />;
    case 'evolution_sources':
      return <EvolutionSourcesDocumentView payload={payload} fallbackMarkdown={normalizedMarkdown} />;
    case 'opportunity_screener':
      return <OpportunityScreenerDocumentView payload={payload} fallbackMarkdown={normalizedMarkdown} />;
    case 'diffable':
      return (
        <GenericDiffDocumentView
          key={`${docDate}__${documentKey}`}
          docDate={docDate}
          documentKey={documentKey}
          payload={payload}
          fallbackMarkdown={normalizedMarkdown}
        />
      );
    default:
      return (
        <SafeMarkdown className="prose prose-invert max-w-none text-sm leading-relaxed">
          {normalizedMarkdown}
        </SafeMarkdown>
      );
  }
}
