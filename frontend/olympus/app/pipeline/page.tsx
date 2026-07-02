import { Suspense } from 'react';
import PipelineClient from '@/components/pipeline/PipelineClient';
import AtlasLoader from '@/components/AtlasLoader';

/**
 * Pipeline hub (Surface 1) — zoomable/pannable graph of the daily decision
 * pipeline (Inputs → Research → Synthesis → Selection → Decision).
 *
 * Deep-link grammar: ?date=YYYY-MM-DD&stage=<stage>&node=<document_key>
 * Replaces the /why redirect placeholder. `PipelineClient` reads the params
 * itself via `useSearchParams()` (this is a static export — no server-side
 * `searchParams` prop is available), which is why it must be Suspense-wrapped
 * here, same as `/why` (`components/why/why-client.tsx`).
 */
export default function PipelinePage() {
  return (
    <div className="flex flex-col flex-1 min-h-0 min-w-0">
      {/* Page header */}
      <header className="px-6 pt-4 pb-2 border-b border-border-subtle">
        <div className="text-[10.5px] font-semibold tracking-[0.16em] uppercase text-text-muted mb-0.5">
          Pipeline
        </div>
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="font-display text-[28px] font-normal leading-none m-0 text-text-primary">
            How today&apos;s decision was made
          </h1>
          <span className="text-[12.5px] text-text-muted">
            research → deliberation → selection
          </span>
        </div>
      </header>

      {/* Client shell */}
      <Suspense fallback={<AtlasLoader fullScreen={false} />}>
        <PipelineClient />
      </Suspense>
    </div>
  );
}
