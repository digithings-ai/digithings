import { Suspense } from 'react';
import PipelineClient from '@/components/pipeline/PipelineClient';
import PageSkeleton from '@/components/page-skeleton';

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
    <main className="flex min-h-0 min-w-0 flex-1 flex-col">
      <Suspense
        fallback={
          <div className="px-6 py-5">
            <PageSkeleton bare />
          </div>
        }
      >
        <PipelineClient />
      </Suspense>
    </main>
  );
}
