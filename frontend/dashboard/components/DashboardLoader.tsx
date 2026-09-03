import { DigiquantMark } from '@digithings/web';

/**
 * Stroke-draw loader over the promoted @digithings/web DigiquantMark (#1548).
 * `strokeClassPrefix` keeps each path classed `research-loader-stroke
 * research-loader-stroke-N`, the hooks the draw keyframes in app/globals.css
 * target — the CSS `stroke: var(--ink)` there outranks the
 * mark's own currentColor presentation attribute, exactly as before.
 * CSS class names stay until the path wave.
 *
 * Default export remains this component so `import … from '@/components/DashboardLoader'`
 * keeps working. Prefer `DigiquantLoader` at new call sites.
 */
function DigiquantLoader(props: { fullScreen?: boolean }) {
  const { fullScreen = true } = props;

  return (
    <div className={fullScreen ? 'research-loader-screen' : 'research-loader-inline'}>
      <div className="research-loader">
        <div className="research-loader-logo" aria-hidden="true">
          <DigiquantMark
            size={56}
            className="research-loader-mark"
            strokeClassPrefix="research-loader-stroke"
          />
        </div>
      </div>
    </div>
  );
}

export default DigiquantLoader;
export { DigiquantLoader, DigiquantLoader as DashboardLoader };
