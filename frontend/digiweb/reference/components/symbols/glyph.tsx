/**
 * Glyph — the interface utility symbol set, as a programmatic name → drawing
 * registry. Every glyph is drawn on a 24×24 viewBox in `currentColor` so it
 * inherits ink/accent from its livery scope: stroke glyphs are monoline at
 * 1.5px with round caps; the GitHub mark is the official Simple Icons path
 * (fill-based), resolved from the `simple-icons` package that @digithings/web
 * already depends on.
 */
import type { ReactNode } from "react";
import { siGithub } from "simple-icons";

interface GlyphDef {
  /** Fill-based mark (e.g. the GitHub octocat); default is 1.5px stroke. */
  filled?: boolean;
  content: ReactNode;
}

const GLYPHS: Record<string, GlyphDef> = {
  github: {
    filled: true,
    content: <path d={siGithub.path} />,
  },
  download: {
    // tray + arrow
    content: (
      <>
        <path d="M12 3.5v10" />
        <path d="M8 9.5l4 4 4-4" />
        <path d="M4 16.5v1.5A2.5 2.5 0 0 0 6.5 20.5h11a2.5 2.5 0 0 0 2.5-2.5v-1.5" />
      </>
    ),
  },
  "sign-in": {
    // door + arrow entering
    content: (
      <>
        <path d="M13 4h4.5A1.5 1.5 0 0 1 19 5.5v13a1.5 1.5 0 0 1-1.5 1.5H13" />
        <path d="M3.5 12H14" />
        <path d="M10.5 8.5L14 12l-3.5 3.5" />
      </>
    ),
  },
  "external-link": {
    content: (
      <>
        <path d="M19 13.5V18a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4.5" />
        <path d="M14.5 4H20v5.5" />
        <path d="M20 4l-9.5 9.5" />
      </>
    ),
  },
  close: {
    content: <path d="M6 6l12 12M18 6L6 18" />,
  },
  menu: {
    content: <path d="M4 7h16M4 12h16M4 17h16" />,
  },
  "chevron-down": {
    content: <path d="M6 9.5l6 6 6-6" />,
  },
  copy: {
    content: (
      <>
        <rect x="9" y="9" width="11.5" height="11.5" rx="2" />
        <path d="M5.5 15h-1A1.5 1.5 0 0 1 3 13.5v-9A1.5 1.5 0 0 1 4.5 3h9A1.5 1.5 0 0 1 15 4.5v1" />
      </>
    ),
  },
  check: {
    content: <path d="M4.5 12.5l5 5L19.5 6.5" />,
  },
  warning: {
    // triangle + stem + dot
    content: (
      <>
        <path d="M12 3.8L2.9 19.4a1.4 1.4 0 0 0 1.2 2.1h15.8a1.4 1.4 0 0 0 1.2-2.1L12 3.8Z" />
        <path d="M12 10v4.5" />
        <path d="M12 17.75h.01" />
      </>
    ),
  },
  search: {
    content: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="M15.5 15.5L21 21" />
      </>
    ),
  },
  theme: {
    // half-moon: outlined disc, right half filled
    content: (
      <>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 3.5a8.5 8.5 0 0 1 0 17Z" fill="currentColor" stroke="none" />
      </>
    ),
  },
};

export const glyphNames = Object.keys(GLYPHS);

export function Glyph({
  name,
  size = 24,
  className,
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  const g = GLYPHS[name];
  if (!g) return null;
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill={g.filled ? "currentColor" : "none"}
      stroke={g.filled ? "none" : "currentColor"}
      strokeWidth={g.filled ? undefined : 1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {g.content}
    </svg>
  );
}
