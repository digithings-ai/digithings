/**
 * ProductFrame — the "real surface, cropped" technique mined from graphite:
 * a product screenshot is authored once on a FIXED 800px artboard, then scaled
 * proportionally to fit its container so it never reflows and stays
 * pixel-faithful at any width. CSS calc() can't derive a unitless scale from
 * lengths, so a ResizeObserver measures the container and writes the factor
 * straight to the node (no per-frame React state). An optional overlay tag
 * labels the crop. Consumes (re-exports) the shared <ProductFrame/> primitive
 * from @digithings/web; the mock tearsheet below is demo content that stays
 * with the reference. Interactive layout template.
 */
export { ProductFrame } from "@digithings/web";

export type MockTearsheetProps = {
  title?: string;
  cagr?: string;
  maxDd?: string;
  profitFactor?: string;
  /** SVG polyline points — override so each crop's chart shape actually differs. */
  points?: string;
};

/**
 * A mock research tearsheet crop — stand-in for a real product screenshot.
 * Every field defaults to the original demo values so existing call sites
 * keep working unchanged, but every ProductFrame consumer on
 * /layout-patterns now passes its own distinct values — before this, all
 * three (feature-cell "research", feature-cell "execution", and this page's
 * standalone demo) rendered byte-identical stats/chart despite different
 * narrative tags, quietly undercutting the section's own "copy leads, the
 * product proves it" claim.
 */
export function MockTearsheet({
  title = "trend_xsec · ETH-USD",
  cagr = "+44.9%",
  maxDd = "-54.1%",
  profitFactor = "2.31",
  points = "0,150 60,140 120,146 180,110 240,120 300,84 360,92 420,54 480,64 560,24",
}: MockTearsheetProps) {
  return (
    <div className="pf-mock">
      <div className="pf-mock-head">
        <span className="pf-mock-title">{title}</span>
      </div>
      <div className="pf-mock-chart" aria-hidden="true">
        <svg viewBox="0 0 560 180" preserveAspectRatio="none">
          <polyline fill="none" stroke="currentColor" strokeWidth="2" points={points} />
        </svg>
      </div>
      <dl className="pf-mock-stats">
        <div>
          <dt>CAGR</dt>
          <dd className="up">{cagr}</dd>
        </div>
        <div>
          <dt>MAX DD</dt>
          <dd className="down">{maxDd}</dd>
        </div>
        <div>
          <dt>PROFIT FACTOR</dt>
          <dd>{profitFactor}</dd>
        </div>
      </dl>
    </div>
  );
}
