"use client";

import { CONVENTIONAL_PARTS, SEAM_LABELS } from "@/lib/whyStack";

/**
 * The two diagrams the why-section composition swaps between (#4429 round 9).
 *
 * Both draw the SAME five rentals, so the reader can map one onto the other:
 * `ConventionalStack` shows them as slabs inside one vendor boundary with the
 * cadence each one bills on; `ModularStack` shows the same set detached, each
 * with the seam you get back, your own endpoints outside the frame, and a slot
 * for the app you build on top.
 *
 * `marks` is the set of part ids the current step lights — the parent computes it
 * from the step index, so the diagrams accumulate annotation as the reader
 * scrolls rather than animating per frame. `progress` is only used for the
 * boundary dissolve and the endpoint drift, and it is a plain number the parent
 * already has, not a per-frame subscription.
 *
 * Nothing here names a vendor and nothing carries a figure. The cadences are
 * cadences.
 */

export type DiagramProps = {
  /** Part ids the current step lights up. */
  marks: string[];
  /** 0 → 1 across the whole stage. */
  progress: number;
};

export function ConventionalStack({ marks }: DiagramProps) {
  const marked = new Set(marks);
  return (
    <svg
      className="whyx-diagram whyx-diagram--rented"
      viewBox="0 0 560 540"
      role="img"
      aria-label="Five rented components inside one vendor boundary, each with the cadence it bills on"
      preserveAspectRatio="xMidYMid meet"
    >
      <rect className="whyx-boundary" x={30} y={44} width={400} height={460} rx={18} />
      <text className="whyx-boundary-label" x={230} y={30} textAnchor="middle">
        one vendor boundary · one release schedule
      </text>

      {CONVENTIONAL_PARTS.map((part, index) => {
        const y = 78 + index * 86;
        const on = marked.has(part.id);
        return (
          <g
            key={part.id}
            className={`whyx-slab${on ? " is-on" : ""}`}
            style={{ "--i": index } as React.CSSProperties}
          >
            <rect className="whyx-slab__box" x={52} y={y} width={356} height={62} rx={6} />
            <text className="whyx-slab__label" x={70} y={y + 26}>
              {part.label}
            </text>
            <text className="whyx-slab__cadence" x={70} y={y + 48}>
              {part.cadence}
            </text>
          </g>
        );
      })}

      {/* The one everybody shares. It gets its own mark because it is the point:
          a rented app is not a differentiator, it is a subscription. */}
      {marked.has("app") ? (
        <text className="whyx-shared" x={470} y={78 + 4 * 86 + 36} textAnchor="middle">
          shared
        </text>
      ) : null}
    </svg>
  );
}

export function ModularStack({ marks, progress }: DiagramProps) {
  const marked = new Set(marks);
  /* The seven layers as three columns of detachable nodes. */
  const nodes: { id: string; x: number; y: number }[] = [
    { id: "models", x: 96, y: 96 },
    { id: "data", x: 96, y: 188 },
    { id: "telemetry", x: 96, y: 280 },
    { id: "hosting", x: 96, y: 372 },
    { id: "app", x: 336, y: 234 },
  ];
  const hubs = [
    { x: 336, y: 140 },
    { x: 336, y: 328 },
    { x: 200, y: 96 },
    { x: 200, y: 372 },
  ];

  return (
    <svg
      className="whyx-diagram whyx-diagram--owned"
      viewBox="0 0 560 540"
      role="img"
      aria-label="The same layers detached, each with the seam you get back, your own endpoints outside the frame, and a slot for the app you build"
      preserveAspectRatio="xMidYMid meet"
    >
      {/* The perimeter is dissolving as you scroll — the boundary is the thing
          you stop paying for. */}
      <rect
        className="whyx-boundary whyx-boundary--fading"
        x={30}
        y={44}
        width={400}
        height={460}
        rx={18}
        style={{ opacity: 0.18 * (1 - Math.min(Math.max(progress, 0), 1)) }}
      />

      <g className="whyx-endpoints" aria-hidden="true">
        <text className="whyx-endpoint" x={470} y={104}>
          your providers
        </text>
        <text className="whyx-endpoint" x={470} y={240}>
          your store
        </text>
        <text className="whyx-endpoint" x={470} y={376}>
          your hosts
        </text>
        <line className="whyx-endpoint-rule" x1={404} y1={100} x2={462} y2={100} />
        <line className="whyx-endpoint-rule" x1={404} y1={236} x2={462} y2={236} />
        <line className="whyx-endpoint-rule" x1={404} y1={372} x2={462} y2={372} />
      </g>

      <g className="whyx-edges" aria-hidden="true">
        {hubs.map((hub, index) => (
          <line key={index} className="whyx-edge" x1={hub.x} y1={hub.y} x2={200} y2={234} />
        ))}
      </g>

      {nodes.map((node, index) => {
        const part = CONVENTIONAL_PARTS.find((entry) => entry.id === node.id);
        const seam = SEAM_LABELS.find((entry) => entry.id === node.id);
        const label = node.id === "app" ? "your app" : (part?.label ?? node.id);
        const on = marked.has(node.id);
        return (
          <g
            key={node.id}
            className={`whyx-node${on ? " is-on" : ""}`}
            transform={`translate(${node.x}, ${node.y})`}
            style={{ "--i": index } as React.CSSProperties}
          >
            <rect className="whyx-node__box" x={-84} y={-26} width={168} height={52} rx={6} />
            <text className="whyx-node__label" x={0} y={2} textAnchor="middle">
              {label}
            </text>
            <text className="whyx-node__seam" x={0} y={22} textAnchor="middle">
              {node.id === "app" ? "REST · MCP · CLI · container" : (seam?.seam ?? "")}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
