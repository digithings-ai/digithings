/**
 * Product brand marks, ported faithfully for the symbols reference page.
 *
 * - DigiChatMark: from frontend/digithings-web/components/DigiChatMark.tsx —
 *   a CLI prompt (`>_`) inside a chat bubble, DigiChat's signature mark.
 * - OlympusMark: from frontend/digiquant-web/components/landing/OlympusMark.tsx
 *   (itself ported from the Olympus dashboard's atlas-mark.tsx). Strokes keep
 *   their `olympus-stroke-N` classes so the dashboard's stroke-draw loader
 *   animation could be replayed via CSS if ever wanted here.
 *
 * Both draw in `currentColor` so they sit on any surface and inherit the
 * ink/accent of their livery scope.
 */

export function DigiChatMark({ size = 18, title }: { size?: number; title?: string }) {
  return (
    <svg
      viewBox="0 0 56 56"
      width={size}
      height={size}
      fill="none"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {title ? <title>{title}</title> : null}
      <rect x="5" y="8" width="46" height="33" rx="10" stroke="currentColor" strokeWidth="2.6" />
      <path
        d="M17 41 L17 50 L28 41"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M16 18 L23 24.5 L16 31"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <rect x="27" y="29" width="12" height="2.6" rx="1.3" fill="currentColor" />
    </svg>
  );
}

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

/**
 * Wordmark — the text lockup grammar shared with the footer colophon:
 * `digi` in ink, the suffix wearing var(--accent) so a livery scope
 * (e.g. `.accent-digiquant`) dresses it automatically. Mono, weight 500.
 */
export function Wordmark({ suffix }: { suffix: string }) {
  return (
    <span className="sym-wordmark">
      digi<em>{suffix}</em>
    </span>
  );
}
