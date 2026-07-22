/**
 * Static heading for the pipeline command band. Hook-free so the server
 * fallback in app/pipeline/page.tsx can prerender it — the static export
 * must carry the h1 before PipelineClient (useSearchParams) hydrates.
 */
export default function PipelineHeading() {
  return (
    <div className="min-w-0">
      <p className="font-mono text-xs font-semibold uppercase text-ink-mute">
        Pipeline
      </p>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="m-0 font-display text-3xl text-ink">
          How today&apos;s decision was made
        </h1>
        <span className="text-sm text-ink-mute">
          research → deliberation → selection
        </span>
      </div>
    </div>
  );
}
