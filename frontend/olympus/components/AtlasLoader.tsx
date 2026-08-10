import { OlympusMark } from '@digithings/web';

/**
 * Stroke-draw loader over the promoted @digithings/web OlympusMark (#1548).
 * `strokeClassPrefix` keeps each path classed `atlas-loader-stroke
 * atlas-loader-stroke-N`, the hooks the draw keyframes in app/globals.css
 * (§Atlas loader) target — the CSS `stroke: var(--ink)` there outranks the
 * mark's own currentColor presentation attribute, exactly as before.
 */
export default function AtlasLoader(props: { fullScreen?: boolean }) {
  const { fullScreen = true } = props;

  return (
    <div className={fullScreen ? 'atlas-loader-screen' : 'atlas-loader-inline'}>
      <div className="atlas-loader">
        <div className="atlas-loader-logo" aria-hidden="true">
          <OlympusMark
            size={56}
            className="atlas-loader-mark"
            strokeClassPrefix="atlas-loader-stroke"
          />
        </div>
      </div>
    </div>
  );
}
