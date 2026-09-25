/**
 * Purpose-built visual per module for the expanded mosaic card (#4429).
 *
 * Data-driven family: every module renders the same order — hero visual,
 * pipeline strip, capability rows, code block, proof ledger — while the hero
 * SVG is unique per module (hub-spoke, tearsheet, funnel, thread-frame,
 * seal-chain, waterfall, ledger-tick, note-graph, fan-in, dashed-cylinder,
 * dashed-chain). Content comes from `data/showcase` (code-verified briefs);
 * roadmap modules render muted with a badge and no runnable snippet.
 *
 * Hero strokes use `--show-accent` (set per module id); everything else is
 * ink/hairline so each card carries exactly one livery.
 */
"use client";

import type { CSSProperties } from "react";

import { DocsCodeBlock } from "../docs/CodeTabs";
import { showcaseFor } from "../../data/showcase";
import type { ModuleNode } from "../../data/modules";
import { cn } from "../../lib/utils";
import { ModuleFlowStrip } from "./ModuleFlow";

const INK = "currentColor";

function HubSpoke() {
  return (
    <g>
      {[28, 60, 92].map((y) => (
        <g key={y}>
          <line x1="40" y1={y} x2="140" y2="60" stroke={INK} strokeWidth="1" opacity="0.55" />
          <circle cx="34" cy={y} r="4" fill="none" stroke={INK} strokeWidth="1.5" />
        </g>
      ))}
      {[24, 48, 72, 96].map((y) => (
        <g key={y}>
          <line x1="180" y1="60" x2="280" y2={y} stroke={INK} strokeWidth="1" opacity="0.55" />
          <rect x="280" y={y - 4} width="8" height="8" fill="none" stroke={INK} strokeWidth="1.5" />
        </g>
      ))}
      <circle cx="160" cy="60" r="16" fill="none" stroke={INK} strokeWidth="2" />
      <circle cx="160" cy="60" r="3" fill={INK} />
    </g>
  );
}

function TearMini() {
  return (
    <g>
      <line x1="20" y1="10" x2="20" y2="110" stroke={INK} strokeWidth="1" opacity="0.4" />
      <line x1="20" y1="110" x2="300" y2="110" stroke={INK} strokeWidth="1" opacity="0.4" />
      <polyline
        points="20,95 60,88 100,92 140,70 180,74 220,50 260,54 300,30"
        fill="none"
        stroke={INK}
        strokeWidth="2"
      />
      <polyline
        points="20,100 60,97 100,95 140,90 180,88 220,84 260,82 300,78"
        fill="none"
        stroke={INK}
        strokeWidth="1"
        strokeDasharray="0.1 5"
        strokeLinecap="round"
        opacity="0.6"
      />
      {[140, 220].map((x) => (
        <line key={x} x1={x} y1="104" x2={x} y2="110" stroke={INK} strokeWidth="1.5" />
      ))}
    </g>
  );
}

function Funnel() {
  const widths = [88, 72, 56, 42, 30];
  return (
    <g>
      {widths.map((w, i) => {
        const x = 30 + i * 52;
        return (
          <g key={i}>
            <rect x={x} y={35} width="34" height="50" fill="none" stroke={INK} strokeWidth="1.5" />
            {[0, 1, 2].map((s) => (
              <line
                key={s}
                x1={x + 6}
                y1={48 + s * 10}
                x2={x + 6 + w / 3.4}
                y2={48 + s * 10}
                stroke={INK}
                strokeWidth="2"
                opacity={0.9 - s * 0.2}
              />
            ))}
            {i < 4 ? (
              <line
                x1={x + 34}
                y1="60"
                x2={x + 52}
                y2="60"
                stroke={INK}
                strokeWidth="1"
                strokeDasharray="4 3"
                opacity="0.6"
              />
            ) : null}
          </g>
        );
      })}
    </g>
  );
}

function ThreadFrame() {
  return (
    <g>
      <rect x="60" y="8" width="200" height="104" fill="none" stroke={INK} strokeWidth="1.5" />
      <line x1="60" y1="8" x2="260" y2="8" stroke={INK} strokeWidth="3" />
      {[
        { y: 30, w: 120, marker: ">" },
        { y: 52, w: 150, marker: "▸" },
        { y: 74, w: 90, marker: "▸" },
      ].map((r, i) => (
        <g key={i}>
          <text x="74" y={r.y} fontSize="11" fill={INK} fontFamily="monospace">
            {r.marker}
          </text>
          <line x1="90" y1={r.y - 4} x2={90 + r.w} y2={r.y - 4} stroke={INK} strokeWidth="2" opacity="0.8" />
        </g>
      ))}
      <rect x={90 + 90} y="68" width="7" height="10" fill={INK} />
    </g>
  );
}

function SealChain() {
  return (
    <g>
      {["key", "token", "verify"].map((_, i) => {
        const x = 60 + i * 100;
        return <circle key={i} cx={x} cy="60" r="10" fill="none" stroke={INK} strokeWidth="1.5" />;
      })}
      <line x1="70" y1="60" x2="150" y2="60" stroke={INK} strokeWidth="1" strokeDasharray="4 3" opacity="0.6" />
      <line x1="170" y1="60" x2="250" y2="60" stroke={INK} strokeWidth="1" strokeDasharray="4 3" opacity="0.6" />
      <rect x="138" y="38" width="44" height="44" fill="none" stroke={INK} strokeWidth="1" opacity="0.7" />
      <rect x="143" y="43" width="34" height="34" fill="none" stroke={INK} strokeWidth="1" opacity="0.45" />
    </g>
  );
}

function Waterfall() {
  return (
    <g>
      {[0, 1, 2].map((i) => (
        <rect
          key={i}
          x={40 + i * 30}
          y={30 + i * 14}
          width="110"
          height="12"
          fill={i === 0 ? INK : "none"}
          stroke={INK}
          strokeWidth="1.5"
          opacity={i === 0 ? 0.9 : 0.6}
        />
      ))}
      <rect x="180" y="72" width="70" height="14" fill={INK} opacity="0.85" />
      <rect x="180" y="94" width="46" height="14" fill={INK} opacity="0.85" />
    </g>
  );
}

function LedgerTick() {
  return (
    <g>
      {[30, 50, 70, 90].map((y) => (
        <line key={y} x1="40" y1={y} x2="280" y2={y} stroke={INK} strokeWidth="1" opacity="0.5" />
      ))}
      <rect x="40" y="42" width="12" height="12" fill={INK} />
      <text x="62" y="52" fontSize="10" fill={INK} fontFamily="monospace" opacity="0.85">
        heartbeat · ok
      </text>
      <text x="62" y="72" fontSize="10" fill={INK} fontFamily="monospace" opacity="0.85">
        reoptimize_triggered
      </text>
      <rect x="228" y="64" width="52" height="12" fill="none" stroke={INK} strokeWidth="1" opacity="0.7" />
      <text x="233" y="73" fontSize="9" fill={INK} fontFamily="monospace" opacity="0.8">
        [SEALED]
      </text>
    </g>
  );
}

function NoteGraph() {
  const nodes: [number, number][] = [
    [160, 55],
    [80, 30],
    [240, 30],
    [90, 90],
    [235, 88],
  ];
  return (
    <g>
      {nodes.slice(1).map(([x, y], i) => (
        <line key={i} x1="160" y1="55" x2={x} y2={y} stroke={INK} strokeWidth="1" opacity="0.55" />
      ))}
      {nodes.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i === 0 ? 7 : 4} fill={i === 0 ? INK : "none"} stroke={INK} strokeWidth="1.5" />
      ))}
      <rect x="140" y="20" width="40" height="12" fill="none" stroke={INK} strokeWidth="1" opacity="0.7" />
      <text x="145" y="29" fontSize="8" fill={INK} fontFamily="monospace">
        [[ ]]
      </text>
      <text x="200" y="108" fontSize="9" fill={INK} fontFamily="monospace" opacity="0.8">
        #tag
      </text>
    </g>
  );
}

function FanIn() {
  return (
    <g>
      {[40, 80, 120, 160, 200, 240, 280].map((x) => (
        <line key={x} x1={x} y1="20" x2="160" y2="78" stroke={INK} strokeWidth="1" opacity="0.55" />
      ))}
      <rect x="70" y="78" width="180" height="22" fill="none" stroke={INK} strokeWidth="1.5" />
      <line x1="70" y1="104" x2="250" y2="104" stroke={INK} strokeWidth="3" />
    </g>
  );
}

function DashedCylinder() {
  return (
    <g opacity="0.8">
      <ellipse cx="160" cy="40" rx="60" ry="14" fill="none" stroke={INK} strokeWidth="1.5" strokeDasharray="6 4" />
      <line x1="100" y1="40" x2="100" y2="90" stroke={INK} strokeWidth="1.5" strokeDasharray="6 4" />
      <line x1="220" y1="40" x2="220" y2="90" stroke={INK} strokeWidth="1.5" strokeDasharray="6 4" />
      <ellipse cx="160" cy="90" rx="60" ry="14" fill="none" stroke={INK} strokeWidth="1.5" strokeDasharray="6 4" />
    </g>
  );
}

function DashedChain() {
  return (
    <g opacity="0.8">
      <rect x="140" y="40" width="40" height="40" fill="none" stroke={INK} strokeWidth="1.5" strokeDasharray="6 4" />
      {[
        [60, 52],
        [220, 52],
        [100, 92],
        [180, 92],
      ].map(([x, y], i) => (
        <g key={i}>
          <rect x={x} y={y} width="20" height="20" fill="none" stroke={INK} strokeWidth="1.5" strokeDasharray="4 3" />
          <line x1={x + 10} y1={y} x2="160" y2="60" stroke={INK} strokeWidth="1" strokeDasharray="3 3" opacity="0.6" />
        </g>
      ))}
    </g>
  );
}

function Hero({ id }: { id: string }) {
  switch (id) {
    case "digigraph":
      return <HubSpoke />;
    case "digiquant":
      return <TearMini />;
    case "digisearch":
      return <Funnel />;
    case "digichat":
      return <ThreadFrame />;
    case "digikey":
      return <SealChain />;
    case "digismith":
      return <Waterfall />;
    case "digiclaw":
      return <LedgerTick />;
    case "digivault":
      return <NoteGraph />;
    case "digibase":
      return <FanIn />;
    case "digistore":
      return <DashedCylinder />;
    default:
      return <DashedChain />;
  }
}

function LedgerTable({ rows }: { rows: { term: string; value: string }[] }) {
  return (
    <dl className="m-show-proof">
      {rows.map((r) => (
        <div key={r.term} className="m-show-proof-row">
          <dt>{r.term}</dt>
          <dd>{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * The expanded card's purpose-built visual: hero motif, pipeline strip,
 * capability rows, runnable snippet, and proof ledger — one livery, one
 * order, every module. Roadmap modules render muted with a badge.
 */
export function ModuleShowcase({ module }: { module: ModuleNode }) {
  const show = showcaseFor(module);
  return (
    <div
      className={cn("m-show", show.planned && "is-planned")}
      style={{ "--show-accent": `var(--accent-${module.id})` } as CSSProperties}
    >
      <svg
        className="m-show-hero"
        viewBox="0 0 320 120"
        role="img"
        aria-label={`${module.name} visual`}
        style={{ color: "var(--show-accent)" }}
      >
        <Hero id={module.id} />
      </svg>
      {show.planned ? (
        <p className="m-show-roadmap">
          <span className="m-show-roadmap-badge">roadmap</span> planned — not yet shippable
        </p>
      ) : null}
      <ModuleFlowStrip stages={show.stages} />
      <ul className="m-show-caps">
        {show.capabilities.map((c) => (
          <li key={c.title}>
            <p className="m-show-cap-title">{c.title}</p>
            <p className="m-show-cap-line">{c.line}</p>
          </li>
        ))}
      </ul>
      {show.snippet ? (
        <div className="m-show-code">
          <p className="m-show-code-lang">{show.snippet.lang}</p>
          <DocsCodeBlock code={show.snippet.code} copyLabel={`Copy ${module.id} snippet`} />
        </div>
      ) : (
        <p className="m-show-planned-note">Planned API — subject to change. No runnable snippet yet.</p>
      )}
      <LedgerTable rows={show.proof} />
    </div>
  );
}
