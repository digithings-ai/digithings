/**
 * Gloomberb candlestick mark — monochrome adaptation of the Gloomberb mark
 * (source gloom-sh/gloomberb, MIT), drawn in currentColor; used to link to
 * the Gloomberb terminal.
 */

export function GloomberbMark({ size = 18, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 512 512"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
      className={['gloomberb-mark', className].filter(Boolean).join(' ')}
    >
      <g transform="translate(256 248) scale(1.15) translate(-256 -248)">
        <rect x="168" y="130" width="14" height="236" rx="7" />
        <rect x="143.5" y="173" width="63" height="150" rx="8" />
        <rect x="249" y="106" width="14" height="284" rx="7" />
        <rect x="220.9" y="149" width="70.2" height="198" rx="8" />
        <rect x="330" y="130" width="14" height="236" rx="7" />
        <rect x="305.5" y="173" width="63" height="150" rx="8" />
      </g>
    </svg>
  );
}
