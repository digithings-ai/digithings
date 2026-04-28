'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { LibraryDocumentView } from '@/lib/queries';
import RebalanceDocumentView from './RebalanceDocumentView';
import DeltaRequestDocumentView from './DeltaRequestDocumentView';
import DeliberationDocumentView from './DeliberationDocumentView';
import DigestDocumentView from './DigestDocumentView';
import EvolutionSourcesDocumentView from './EvolutionSourcesDocumentView';
import OpportunityScreenerDocumentView from './OpportunityScreenerDocumentView';
import GenericDiffDocumentView from './GenericDiffDocumentView';

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

  if (view === 'markdown' && isDigest && docDate) {
    return <DigestDocumentView key={docDate} docDate={docDate} fallbackMarkdown={markdown} />;
  }

  switch (view) {
    case 'rebalance':
      return <RebalanceDocumentView payload={payload} fallbackMarkdown={markdown} />;
    case 'delta_request':
      return <DeltaRequestDocumentView payload={payload} />;
    case 'deliberation':
      return <DeliberationDocumentView payload={payload} fallbackMarkdown={markdown} />;
    case 'evolution_sources':
      return <EvolutionSourcesDocumentView payload={payload} fallbackMarkdown={markdown} />;
    case 'opportunity_screener':
      return <OpportunityScreenerDocumentView payload={payload} fallbackMarkdown={markdown} />;
    case 'diffable':
      return (
        <GenericDiffDocumentView
          key={`${docDate}__${documentKey}`}
          docDate={docDate}
          documentKey={documentKey}
          payload={payload}
          fallbackMarkdown={markdown}
        />
      );
    default:
      return (
        <div className="prose prose-invert max-w-none text-sm leading-relaxed">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
        </div>
      );
  }
}
