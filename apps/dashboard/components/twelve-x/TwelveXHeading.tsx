/**
 * Off-screen page heading for the FX Hub. The workspace shows only the tab
 * bar at the top of the page (no title/date banner) — but the static export
 * still needs a real h1 to prerender before TwelveXClient hydrates (same
 * convention as components/pipeline/PipelineHeading.tsx), and screen readers
 * still need a page title even when it isn't shown visually.
 */
export default function TwelveXHeading() {
  return <h1 className="sr-only">FX Hub</h1>;
}
