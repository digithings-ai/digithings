"use client";
/**
 * Scrollytelling module graph. Desktop: a pinned graph whose focus advances
 * node-by-node with scroll, a side panel describing the focused module. Mobile
 * or reduced-motion: a static vertical stepper of module cards. Reuses the
 * v1 graph geometry + activation logic (active node + incident edges + neighbours).
 */
import { useEffect, useRef, useState } from "react";
import { useScroll, useMotionValueEvent } from "framer-motion";
import { modules, edges, type ModuleNode } from "../data/modules";
import { Emblem } from "./emblems";
import { StackRow } from "./StackLogo";

const ordered = [...modules].sort((a, b) => a.graphOrder - b.graphOrder);

function neighboursOf(id: string): Set<string> {
  const near = new Set<string>([id]);
  for (const e of edges) {
    if (e.a === id) near.add(e.b);
    if (e.b === id) near.add(e.a);
  }
  return near;
}

export function GraphSVG({ activeId, onPick }: { activeId: string | null; onPick: (id: string) => void }) {
  const near = activeId ? neighboursOf(activeId) : null;
  return (
    <svg className="dg-graph" viewBox="0 0 920 560" role="img" aria-label="digithings module graph" preserveAspectRatio="xMidYMid meet">
      <g>
        {edges.map((e, i) => {
          const a = modules.find((m) => m.id === e.a)!.graph;
          const b = modules.find((m) => m.id === e.b)!.graph;
          const active = activeId != null && (e.a === activeId || e.b === activeId);
          return (
            <line key={i} className={`dg-edge${active ? " on" : ""}${near ? " has-active" : ""}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
          );
        })}
      </g>
      <g>
        {modules.map((m) => {
          const dim = near != null && !near.has(m.id);
          const on = m.id === activeId;
          return (
            <g key={m.id} className={`dg-node${m.graph.hub ? " hub" : ""}${on ? " on" : ""}${dim ? " dim" : ""}`}
              transform={`translate(${m.graph.x} ${m.graph.y})`} tabIndex={0} role="button"
              aria-label={m.name} onClick={() => onPick(m.id)}
              onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); onPick(m.id); } }}>
              <circle className="halo" r={m.graph.r + 12} />
              <circle className="node" r={m.graph.r} />
              <text className="label" y={m.graph.r + 18}>{m.name}</text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}

function ModulePanel({ m }: { m: ModuleNode }) {
  return (
    <div className="dg-panel" key={m.id}>
      <div className="dg-panel-head">
        <Emblem id={m.emblem} size={40} />
        <div>
          <span className={`dg-tier t-${m.tier}`}>{m.tier === "roadmap" ? "roadmap" : m.tier}</span>
          <h3>{m.name}</h3>
        </div>
      </div>
      <p className="dg-tag">{m.tagline}</p>
      <StackRow items={m.stack} />
      {m.dockerCmd && (
        <div className="dg-docker"><span className="prompt">$</span> {m.dockerCmd}</div>
      )}
      <a className="dg-more" href={`/modules/${m.id}`}>man {m.id} →</a>
    </div>
  );
}

export function ScrollyGraph() {
  const trackRef = useRef<HTMLDivElement>(null);
  const [idx, setIdx] = useState(0);
  const [hover, setHover] = useState<string | null>(null);
  const [stepper, setStepper] = useState(false);

  useEffect(() => {
    const mq = matchMedia("(max-width: 860px), (prefers-reduced-motion: reduce)");
    const apply = () => setStepper(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  const { scrollYProgress } = useScroll({ target: trackRef, offset: ["start start", "end end"] });
  useMotionValueEvent(scrollYProgress, "change", (p) => {
    const n = ordered.length;
    setIdx(Math.max(0, Math.min(n - 1, Math.floor(p * n))));
  });

  if (stepper) {
    return (
      <div className="dg-stepper">
        {ordered.map((m) => (
          <article className="dg-step" key={m.id}>
            <GraphMini activeId={m.id} />
            <ModulePanel m={m} />
          </article>
        ))}
      </div>
    );
  }

  const activeId = hover ?? ordered[idx].id;
  const activeMod = modules.find((m) => m.id === activeId)!;
  return (
    <div ref={trackRef} className="dg-track" style={{ height: `${ordered.length * 90}vh` }}>
      <div className="dg-stage">
        <div className="dg-stage-grid">
          <div className="dg-graph-wrap"
            onMouseLeave={() => setHover(null)}
            onMouseOver={(e) => {
              const g = (e.target as Element).closest?.(".dg-node") as SVGGElement | null;
              const lbl = g?.getAttribute("aria-label");
              if (lbl) setHover(modules.find((m) => m.name === lbl)?.id ?? null);
            }}>
            <GraphSVG activeId={activeId} onPick={(id) => { location.href = `/modules/${id}`; }} />
          </div>
          <ModulePanel m={activeMod} />
        </div>
        <div className="dg-rail" aria-hidden="true">
          {ordered.map((m, i) => (
            <span key={m.id} className={`dg-tick${i === idx ? " on" : ""}`} />
          ))}
        </div>
      </div>
    </div>
  );
}

/** Small static graph used in the mobile stepper (one node highlighted). */
function GraphMini({ activeId }: { activeId: string }) {
  return (
    <div className="dg-graph-mini">
      <GraphSVG activeId={activeId} onPick={() => {}} />
    </div>
  );
}
