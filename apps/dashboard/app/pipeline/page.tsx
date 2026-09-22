import { Suspense } from 'react';
import PipelineClient from '@/components/pipeline/PipelineClient';
import PageSkeleton from '@/components/page-skeleton';

/**
 * Pipeline hub (Surface 1) — zoomable/pannable graph of the daily decision
 * pipeline (Inputs → Research → Synthesis → Selection → Decision).
 *
 * Deep-link grammar: ?date=YYYY-MM-DD&stage=<stage>&node=<document_key>
 * `PipelineClient` reads the params itself via `useSearchParams()` (this is a
 * static export — no server-side `searchParams` prop is available), which is
 * why it must be Suspense-wrapped here, same as `/why`.
 *
 * The workspace intentionally has no visible page heading — the compact
 * command band maximizes canvas space — so the accessible h1 is sr-only and
 * mirrored in the fallback to keep the prerendered artifact carrying an h1
 * (check-static-export pins this).
 */
export default function PipelinePage() {
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <Suspense
        fallback={
          <>
            <h1 className="sr-only">Pipeline</h1>
            <div className="px-6 py-5">
              <PageSkeleton bare />
            </div>
          </>
        }
      >
        <PipelineClient />
      </Suspense>
    </div>
  );
}
