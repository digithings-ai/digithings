"use client";

import { useRef } from "react";
import { useInView } from "motion/react";
import { ChatWidgetFrame } from "@digithings/web";

/**
 * Inline route graph — a small SVG supervisor→agent flow graph rendered inline in
 * an assistant turn, drawing its edges when scrolled into view. The term-surface
 * frame is the shared <ChatWidgetFrame variant="embed"> (@digithings/web); the
 * SVG internals (.route-* paint + draw keyframes, chatbot.css) stay specimen-side.
 */
type Node = { id: string; x: number; y: number; w: number; label: string };

const NODES: Node[] = [
  { id: "you", x: 20, y: 84, w: 44, label: "you" },
  { id: "sup", x: 104, y: 84, w: 92, label: "supervisor" },
  { id: "quant", x: 244, y: 30, w: 88, label: "digiquant" },
  { id: "search", x: 244, y: 138, w: 92, label: "digisearch" },
  { id: "vault", x: 372, y: 84, w: 56, label: "vault" },
];

const NODE_H = 30;
const byId = (id: string) => NODES.find((n) => n.id === id)!;

// right-edge → left-edge cubic between two nodes
function edge(fromId: string, toId: string) {
  const a = byId(fromId);
  const b = byId(toId);
  const x1 = a.x + a.w;
  const y1 = a.y + NODE_H / 2;
  const x2 = b.x;
  const y2 = b.y + NODE_H / 2;
  const mx = (x1 + x2) / 2;
  return `M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`;
}

const EDGES = [
  ["you", "sup"],
  ["sup", "quant"],
  ["sup", "search"],
  ["quant", "vault"],
  ["search", "vault"],
];

export function ChatInlineGraphReference() {
  const scopeRef = useRef<HTMLDivElement | null>(null);
  const inView = useInView(scopeRef, { amount: 0.5, once: true });

  return (
    <section className="section-block" ref={scopeRef}>
      <p className="kicker">{"// inline graph"}</p>
      <h2 className="title">The route it took.</h2>
      <p className="section-copy">
        Not every graphic is a time series. When the answer is a structure — how a request was
        routed, which tools fired — the assistant draws a node-link graph. Edges trace in on the
        accent when it enters view; reduced motion renders it settled.
      </p>

      <div className="chat-surface mt-[1.3rem] max-w-[760px] flex flex-col gap-[0.7rem] rounded-[12px] border border-term-hair bg-term-bg px-[1.15rem] pt-[1rem] pb-[1.2rem] font-mono">
        <div className="flex gap-[0.55rem] items-baseline chat-turn--assistant">
          <span className="shrink-0 font-mono text-[0.86rem] leading-[1.5] text-accent" aria-hidden="true">
            ▸
          </span>
          <div className="min-w-0 border-0 rounded-none bg-transparent p-0 text-ink-soft text-[0.88rem] leading-[1.6]">
            <p className="m-0 mb-[0.55rem] text-ink-soft text-[0.85rem]">
              Here&apos;s how I routed that request:
            </p>
            <ChatWidgetFrame variant="embed">
              <svg
                className={`route-graph w-full h-auto${inView ? " in" : ""}`}
                viewBox="0 0 448 192"
                role="img"
                aria-label="Request routed from you to the supervisor, out to digiquant and digisearch, then saved to the vault"
              >
                {EDGES.map(([f, t]) => (
                  <path key={`${f}-${t}`} className="route-edge" d={edge(f, t)} />
                ))}
                {NODES.map((n) => (
                  <g key={n.id} className={`route-node route-node--${n.id}`}>
                    <rect x={n.x} y={n.y} width={n.w} height={NODE_H} rx={8} />
                    <text x={n.x + n.w / 2} y={n.y + NODE_H / 2 + 3.5}>
                      {n.label}
                    </text>
                  </g>
                ))}
              </svg>
            </ChatWidgetFrame>
          </div>
        </div>
      </div>
    </section>
  );
}
