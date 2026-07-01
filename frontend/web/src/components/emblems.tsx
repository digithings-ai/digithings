/**
 * Module emblem family — one minimal, modern visual grammar across modules.
 * Each mark is a single geometric idea representing what the module does, drawn
 * on a 0 0 32 32 grid (centered at 16,16), monoline with round caps and exactly
 * one filled accent element for hierarchy. Stroke + fill use `currentColor`; the
 * `Emblem` wrapper sets that to the module's own accent token, so each renders in
 * its own colour while staying a single, cohesive set.
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
    strokeWidth={2.2}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    {...rest}
  >
    <g transform="translate(16 16)">{children}</g>
  </svg>
);

// orchestration — a supervisor hub branching to specialist nodes
const DigiGraph = (p: P) => (
  <Svg {...p}>
    <circle cx="0" cy="-4" r="4.3" fill="currentColor" stroke="none" />
    <circle cx="-10" cy="10" r="3" />
    <circle cx="10" cy="10" r="3" />
    <path d="M-3 -1 -8 6M3 -1 8 6" />
  </Svg>
);
// quant — ascending candles, the leader filled (research that ends in an order)
const DigiQuant = (p: P) => (
  <Svg {...p}>
    <rect x="-13" y="2" width="6" height="11" rx="2" />
    <rect x="-3" y="-5" width="6" height="18" rx="2" />
    <rect x="7" y="-12" width="6" height="25" rx="2" fill="currentColor" stroke="none" />
  </Svg>
);
// retrieval — a lens over a focal point (vector search)
const DigiSearch = (p: P) => (
  <Svg {...p}>
    <circle cx="-3" cy="-3" r="10" />
    <path d="M5 5 13 13" />
    <circle cx="-3" cy="-3" r="2.4" fill="currentColor" stroke="none" />
  </Svg>
);
// chat — a terminal prompt (`>_`)
const DigiChat = (p: P) => (
  <Svg {...p}>
    <path d="M-10 -8 -1 0 -10 8" />
    <path d="M3 8 13 8" />
  </Svg>
);
// auth — a key with cut bits
const DigiKey = (p: P) => (
  <Svg {...p}>
    <circle cx="-7" cy="-7" r="5.5" />
    <path d="M-3 -3 11 11M7 7 11 3M9 9 13 5" />
  </Svg>
);
// observability — offset trace spans, the lead span filled
const DigiSmith = (p: P) => (
  <Svg {...p}>
    <rect x="-13" y="-11" width="16" height="5.5" rx="2.75" fill="currentColor" stroke="none" />
    <rect x="-5" y="-2" width="18" height="5.5" rx="2.75" />
    <rect x="-10" y="7" width="13" height="5.5" rx="2.75" />
  </Svg>
);
// runtime — a heartbeat closed in a ring (always-on, on an interval)
const DigiClaw = (p: P) => (
  <Svg {...p}>
    <circle cx="0" cy="0" r="12" />
    <path d="M-8 0 -3 0 -1 -6 2 6 4 0 8 0" />
  </Svg>
);
// library — stacked layers on a filled base (the foundation everything builds on)
const DigiBase = (p: P) => (
  <Svg {...p}>
    <rect x="-14" y="-11" width="28" height="5.5" rx="2" />
    <rect x="-14" y="-3" width="28" height="5.5" rx="2" />
    <rect x="-14" y="5" width="28" height="5.5" rx="2" fill="currentColor" stroke="none" />
  </Svg>
);
// storage (roadmap) — a database cylinder
const DigiStore = (p: P) => (
  <Svg {...p}>
    <ellipse cx="0" cy="-9" rx="12" ry="3.5" />
    <path d="M-12 -9 -12 9c0 2 5.4 3.5 12 3.5s12 -1.5 12 -3.5V-9" />
  </Svg>
);
// link (roadmap) — two interlocking rings, one tinted (protocol bridge)
const DigiLink = (p: P) => (
  <Svg {...p}>
    <circle cx="-5" cy="0" r="7.5" />
    <circle cx="5" cy="0" r="7.5" fill="currentColor" fillOpacity="0.16" />
  </Svg>
);
// subsystems — research scheduler (globe), signal messenger (send), execution timing (clock)
const Atlas = (p: P) => (
  <Svg {...p}>
    <circle cx="0" cy="0" r="12" />
    <path d="M0 -12a5 12 0 0 0 0 24a5 12 0 0 0 0 -24" />
    <path d="M-12 0 12 0" />
  </Svg>
);
const Hermes = (p: P) => (
  <Svg {...p}>
    <path d="M-11 11 11 -11" />
    <path d="M11 -11 3 -11M11 -11 11 -3" />
    <circle cx="-11" cy="11" r="1.6" fill="currentColor" stroke="none" />
  </Svg>
);
const Kairos = (p: P) => (
  <Svg {...p}>
    <circle cx="0" cy="0" r="12" />
    <path d="M0 0 0 -7M0 0 5 3" />
    <circle cx="0" cy="0" r="1.6" fill="currentColor" stroke="none" />
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
