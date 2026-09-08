import type { FC } from "react";

const SQUARE_STROKE = {
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "square" as const,
  strokeLinejoin: "miter" as const,
};

export const CopyActionIcon: FC<{ className?: string }> = ({ className }) => (
  <svg className={className} viewBox="0 0 16 16" fill="none" aria-hidden>
    <rect x="5.5" y="5.5" width="8" height="8" fill="none" {...SQUARE_STROKE} />
    <path d="M10.5 2.5H2.5v8" fill="none" {...SQUARE_STROKE} />
  </svg>
);

export const CheckActionIcon: FC<{ className?: string }> = ({ className }) => (
  <svg className={className} viewBox="0 0 16 16" fill="none" aria-hidden>
    <path d="M3 8.5 6.5 12 13 4" fill="none" {...SQUARE_STROKE} />
  </svg>
);

export const CloseActionIcon: FC<{ className?: string }> = ({ className }) => (
  <svg className={className} viewBox="0 0 16 16" fill="none" aria-hidden>
    <path d="M4 4 12 12" fill="none" {...SQUARE_STROKE} />
    <path d="M12 4 4 12" fill="none" {...SQUARE_STROKE} />
  </svg>
);

export const PlusActionIcon: FC<{ className?: string }> = ({ className }) => (
  <svg className={className} viewBox="0 0 16 16" fill="none" aria-hidden>
    <path d="M8 3v10" fill="none" {...SQUARE_STROKE} />
    <path d="M3 8h10" fill="none" {...SQUARE_STROKE} />
  </svg>
);
