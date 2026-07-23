/**
 * Static heading for the FX Research command band. Hook-free so the server
 * fallback in app/twelve-x/page.tsx can prerender it — the static export must
 * carry the h1 before TwelveXClient hydrates (same convention as
 * components/pipeline/PipelineHeading.tsx).
 */
export default function TwelveXHeading() {
  return (
    <div className="min-w-0">
      <p className="font-mono text-xs font-semibold uppercase text-ink-mute">
        FX Research
      </p>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="m-0 font-display text-3xl text-ink">
          Where the desks agree
        </h1>
        <span className="text-sm text-ink-mute">
          desk research → consensus → conviction
        </span>
      </div>
    </div>
  );
}
