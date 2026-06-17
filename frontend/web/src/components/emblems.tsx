/**
 * Bespoke monoline emblem family — one visual grammar across modules.
 * viewBox 0 0 32 32, stroke=currentColor (= --accent), no fill, round caps.
 * Size via the `size` prop; color via container `color`/`currentColor`.
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
    strokeWidth={1.75}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    {...rest}
  >
    {children}
  </svg>
);

// orchestration — central hub branching to satellites
const DigiGraph = (p: P) => (
  <Svg {...p}>
    <circle cx="16" cy="16" r="3.2" />
    <circle cx="6" cy="7" r="2" /><circle cx="26" cy="8" r="2" /><circle cx="25" cy="25" r="2" />
    <path d="M13.4 14.2 7.6 8.6M18.7 14.4 24.2 9.4M18.2 18.1 23.4 23.3" />
  </Svg>
);
// quant — candles + rising curve
const DigiQuant = (p: P) => (
  <Svg {...p}>
    <path d="M5 20l6-4 5 3 6-7 5 3" />
    <path d="M9 24v-3M9 16v-2M20 22v-3M20 13v-2" />
    <rect x="7" y="14" width="4" height="7" rx="1" /><rect x="18" y="11" width="4" height="6" rx="1" />
  </Svg>
);
// retrieval — lens + vector points
const DigiSearch = (p: P) => (
  <Svg {...p}>
    <circle cx="13" cy="13" r="7" /><path d="M18.5 18.5 26 26" />
    <circle cx="10.5" cy="13" r="0.6" fill="currentColor" /><circle cx="13" cy="11" r="0.6" fill="currentColor" /><circle cx="15.5" cy="14" r="0.6" fill="currentColor" />
  </Svg>
);
// chat — prompt chevron in a bubble
const DigiChat = (p: P) => (
  <Svg {...p}>
    <path d="M6 8h20a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H14l-6 5v-5H6a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2z" />
    <path d="M11 12l3 2.5-3 2.5M17 17h4" />
  </Svg>
);
// auth — key
const DigiKey = (p: P) => (
  <Svg {...p}>
    <circle cx="11" cy="12" r="5" /><path d="M14.5 15.5 25 26M21 22l3-3M24 25l3-3" />
  </Svg>
);
// observability — waveform crossed by span ticks
const DigiSmith = (p: P) => (
  <Svg {...p}>
    <path d="M4 18l4-6 4 9 4-13 4 10 4-5 4 5" />
    <path d="M8 24v3M16 24v3M24 24v3" opacity="0.7" />
  </Svg>
);
// runtime — heartbeat in a ring
const DigiClaw = (p: P) => (
  <Svg {...p}>
    <circle cx="16" cy="16" r="12" />
    <path d="M7 16h4l2-4 3 8 2-4h7" />
  </Svg>
);
// library — stacked bars
const DigiBase = (p: P) => (
  <Svg {...p}>
    <path d="M10 8h12M7 16h18M5 24h22" />
  </Svg>
);
// storage (roadmap) — DB cylinder + swap arrow
const DigiStore = (p: P) => (
  <Svg {...p}>
    <ellipse cx="16" cy="9" rx="9" ry="3.2" /><path d="M7 9v14c0 1.8 4 3.2 9 3.2s9-1.4 9-3.2V9" />
    <path d="M12 16h8M18 13l3 3-3 3" opacity="0.8" />
  </Svg>
);
// link (roadmap) — interlocking links bridging a gap
const DigiLink = (p: P) => (
  <Svg {...p}>
    <path d="M13 10a5 5 0 0 0 0 12h2M19 10h2a5 5 0 0 1 0 12" /><path d="M12 16h8" />
  </Svg>
);
// subsystems
const Atlas = (p: P) => (
  <Svg {...p}>
    <circle cx="16" cy="16" r="11" /><path d="M16 5c4 3 4 19 0 22M16 5c-4 3-4 19 0 22M5.5 13h21M5.5 19h21" opacity="0.85" />
  </Svg>
);
const Hermes = (p: P) => (
  <Svg {...p}>
    <path d="M6 22l14-12M20 10h-6M20 10v6" /><path d="M6 14l5-4M9 26l4-4" opacity="0.7" />
  </Svg>
);
const Kairos = (p: P) => (
  <Svg {...p}>
    <path d="M8 6v20M24 6v20" /><path d="M8 11h16M8 16h16M8 21h16" opacity="0.85" />
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
  return <span className={className} style={{ display: "inline-flex", color: "var(--accent)" }}>{E({ size })}</span>;
}
