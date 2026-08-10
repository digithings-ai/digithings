/**
 * The real Olympus brand mark, ported verbatim from the Olympus dashboard
 * (frontend/olympus/components/atlas-mark.tsx) so digiquant.io matches it.
 * Strokes carry `olympus-stroke-N` classes so the dashboard's loader animation
 * (stroke-draw + scale pulse) can be replayed on hover via CSS (see globals.css).
 * Uses currentColor, so it inherits the surrounding text/button colour.
 */
export function OlympusMark({ size = 22, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      aria-hidden="true"
      focusable="false"
      className={["olympus-mark", className].filter(Boolean).join(" ")}
    >
      <path
        className="olympus-stroke olympus-stroke-1"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4.2774,32.5293a11.6485,11.6485,0,0,1,23.2219,1.32h0c0,3.2166.0022,11.6479.0022,11.6479"
      />
      <path
        className="olympus-stroke olympus-stroke-2"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3.3047,29.8574q-.0277-.4816-.0279-.97a16.61,16.61,0,1,1,33.2209,0v0c0,4.5869.0031,16.6095.0031,16.6095"
      />
      <circle
        className="olympus-stroke olympus-stroke-3"
        stroke="currentColor"
        strokeWidth="2"
        cx="16.5007"
        cy="33.4992"
        r="5.0328"
      />
      <path
        className="olympus-stroke olympus-stroke-4"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M45.5,24A21.5,21.5,0,1,0,24,45.5H45.5Z"
      />
    </svg>
  );
}
