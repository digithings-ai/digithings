/**
 * Module emblem family — one modern visual grammar across modules. Each mark
 * is a single geometric idea representing what the module does, drawn on a
 * 0 0 32 32 grid (centered at 16,16). The grammar is dual-tone but single-hue:
 * a monoline silhouette in `currentColor`, one soft `currentColor` tint layer
 * (fillOpacity ~0.15) for figure/ground depth, and at most one solid accent
 * detail for focus. The `Emblem` wrapper sets `currentColor` to the module's
 * own accent token, so each renders in its own colour while the set stays
 * cohesive.
 */
import { type SVGProps } from "react";

type P = { size?: number } & SVGProps<SVGSVGElement>;
const Svg = ({ size = 32, children, ...rest }: P & { children: React.ReactNode }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 32 32"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    {...rest}
  >
    <g transform="translate(16 16)">{children}</g>
  </svg>
);

/** Soft same-hue fill for the depth layer — figure/ground without a 2nd colour. */
const TINT = 0.15;

// orchestration — a supervisor hub branching to three specialist nodes
const DigiGraph = (p: P) => (
  <Svg {...p}>
    <path d="M0 -6 -9 8M0 -6 0 8M0 -6 9 8" />
    <circle cx="0" cy="-6" r="5.4" fill="currentColor" fillOpacity={TINT} stroke="none" />
    <circle cx="0" cy="-6" r="4.4" fill="currentColor" stroke="none" />
    <circle cx="-9" cy="9" r="2.7" />
    <circle cx="0" cy="9" r="2.7" />
    <circle cx="9" cy="9" r="2.7" />
  </Svg>
);
// quant — ascending candlesticks with wicks, the leader filled (research → order)
const DigiQuant = (p: P) => (
  <Svg {...p}>
    <path d="M-9.5 0v13" />
    <rect x="-12" y="3" width="5" height="9" rx="1.6" fill="currentColor" fillOpacity={TINT} />
    <path d="M0 -7v19" />
    <rect x="-2.5" y="-2" width="5" height="13" rx="1.6" fill="currentColor" fillOpacity={TINT} />
    <path d="M9.5 -13v26" />
    <rect x="7" y="-9" width="5" height="20" rx="1.6" fill="currentColor" stroke="none" />
  </Svg>
);
// retrieval — a lens over a focal point (vector search)
const DigiSearch = (p: P) => (
  <Svg {...p}>
    <circle cx="-3" cy="-3" r="9.5" fill="currentColor" fillOpacity={TINT} />
    <path d="M4.5 4.5 12.5 12.5" />
    <circle cx="-3" cy="-3" r="2.6" fill="currentColor" stroke="none" />
  </Svg>
);
// chat — a terminal prompt: a chevron and a solid block cursor (no bubble)
const DigiChat = (p: P) => (
  <Svg {...p}>
    <path d="M-9 -5.5 -2 0 -9 5.5" />
    <rect x="2" y="-5" width="6.5" height="10" rx="1" fill="currentColor" stroke="none" />
  </Svg>
);
// auth — a rounded key: soft-filled bow, notched shaft
const DigiKey = (p: P) => (
  <Svg {...p}>
    <circle cx="-6" cy="-6" r="6" fill="currentColor" fillOpacity={TINT} />
    <circle cx="-6" cy="-6" r="2.2" fill="currentColor" stroke="none" />
    <path d="M-1.7 -1.7 11 11M6.5 6.5 10.5 2.5M9 9 13 5" />
  </Svg>
);
// observability — a trace waterfall, the lead span filled
const DigiSmith = (p: P) => (
  <Svg {...p}>
    <rect x="-13" y="-11" width="15" height="5" rx="2.5" fill="currentColor" stroke="none" />
    <rect
      x="-6"
      y="-2.5"
      width="19"
      height="5"
      rx="2.5"
      fill="currentColor"
      fillOpacity={TINT}
    />
    <rect x="-10" y="6" width="12" height="5" rx="2.5" fill="currentColor" fillOpacity={TINT} />
  </Svg>
);
// runtime — a heartbeat sealed in a ring (always-on, on an interval)
const DigiClaw = (p: P) => (
  <Svg {...p}>
    <circle cx="0" cy="0" r="12" fill="currentColor" fillOpacity={TINT} />
    <path d="M-8.5 0 -4 0 -1.5 -6 1.5 6 4 0 8.5 0" />
  </Svg>
);
// library — stacked layers on a filled foundation (what everything builds on)
const DigiBase = (p: P) => (
  <Svg {...p}>
    <rect x="-13" y="-11.5" width="26" height="5.2" rx="2" fill="currentColor" fillOpacity={TINT} />
    <rect x="-13" y="-3.5" width="26" height="5.2" rx="2" fill="currentColor" fillOpacity={TINT} />
    <rect x="-13" y="4.5" width="26" height="5.2" rx="2" fill="currentColor" stroke="none" />
  </Svg>
);
// storage (roadmap) — a database cylinder with a soft-filled cap
const DigiStore = (p: P) => (
  <Svg {...p}>
    <path
      d="M-12 -9v18c0 2 5.4 3.5 12 3.5s12 -1.5 12 -3.5V-9"
      fill="currentColor"
      fillOpacity={TINT}
    />
    <ellipse cx="0" cy="-9" rx="12" ry="3.5" fill="currentColor" fillOpacity={TINT} />
    <path d="M-12 0c0 2 5.4 3.5 12 3.5s12 -1.5 12 -3.5" />
  </Svg>
);
// link (roadmap) — two interlocking chain links, one tinted (protocol bridge)
const DigiLink = (p: P) => (
  <Svg {...p}>
    <rect x="-13" y="-5.5" width="15" height="11" rx="5.5" fill="currentColor" fillOpacity={TINT} />
    <rect x="-2" y="-5.5" width="15" height="11" rx="5.5" />
  </Svg>
);
// atlas — research scheduler: a globe with meridian + equator
const Atlas = (p: P) => (
  <Svg {...p}>
    <circle cx="0" cy="0" r="12" fill="currentColor" fillOpacity={TINT} />
    <path d="M0 -12a5 12 0 0 0 0 24a5 12 0 0 0 0 -24" />
    <path d="M-12 0 12 0" />
  </Svg>
);
// hermes — signal messenger: a paper-plane send mark, filled
const Hermes = (p: P) => (
  <Svg {...p}>
    <path
      d="M13 -12 -12 -1 -1 3 3 12 13 -12z"
      fill="currentColor"
      fillOpacity={TINT}
    />
    <path d="M13 -12 -1 3" />
    <circle cx="-1" cy="3" r="1.7" fill="currentColor" stroke="none" />
  </Svg>
);
// kairos — execution timing: a clock, one tick struck to mark the moment
const Kairos = (p: P) => (
  <Svg {...p}>
    <circle cx="0" cy="0" r="12" fill="currentColor" fillOpacity={TINT} />
    <path d="M0 -12 0 -9" stroke="currentColor" strokeWidth="2.6" />
    <path d="M0 0 0 -6.5M0 0 4.5 2.5" />
    <circle cx="0" cy="0" r="1.7" fill="currentColor" stroke="none" />
  </Svg>
);

export const emblems: Record<string, (p: P) => React.ReactNode> = {
  digigraph: DigiGraph, digiquant: DigiQuant, digisearch: DigiSearch, digichat: DigiChat,
  digikey: DigiKey, digismith: DigiSmith, digiclaw: DigiClaw, digibase: DigiBase,
  digistore: DigiStore, digilink: DigiLink, atlas: Atlas, hermes: Hermes, kairos: Kairos,
};

export function Emblem({ id, size = 32, className }: { id: string; size?: number; className?: string }) {
  const E = emblems[id];
  if (!E) return null;
  // Per-module accent (--accent-<id>, defined at :root in tokens.css), falling back
  // to the page accent. The platform accent is neutralized on digithings.ai, but the
  // per-module tokens keep their colour, so emblems carry the module's own hue.
  return (
    <span className={className} style={{ display: "inline-flex", color: `var(--accent-${id}, var(--accent))` }}>
      {E({ size })}
    </span>
  );
}
