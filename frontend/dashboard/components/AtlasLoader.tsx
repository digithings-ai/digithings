import { DigiquantMark } from '@digithings/web';

/**
 * Stroke-draw loader over the promoted @digithings/web DigiquantMark (#1548).
 * `strokeClassPrefix` keeps each path classed `atlas-loader-stroke
 * atlas-loader-stroke-N`, the hooks the draw keyframes in app/globals.css
 * target — the CSS `stroke: var(--ink)` there outranks the
 * mark's own currentColor presentation attribute, exactly as before.
 * CSS class names stay until the path wave.
 *
 * Default export remains this component so `import … from '@/components/AtlasLoader'`
 * keeps working. Prefer `DigiquantLoader` at new call sites.
 */
function DigiquantLoader(props: { fullScreen?: boolean }) {
  const { fullScreen = true } = props;

  return (
    <div className={fullScreen ? 'atlas-loader-screen' : 'atlas-loader-inline'}>
      <div className="atlas-loader">
        <div className="atlas-loader-logo" aria-hidden="true">
          <DigiquantMark
            size={56}
            className="atlas-loader-mark"
            strokeClassPrefix="atlas-loader-stroke"
          />
        </div>
      </div>
    </div>
  );
}

export default DigiquantLoader;
export { DigiquantLoader, DigiquantLoader as AtlasLoader };
