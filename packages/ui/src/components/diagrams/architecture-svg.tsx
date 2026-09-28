/**
 * Architecture SVG — the box-and-connector renderer.
 *
 * WHY NOT MERMAID'S `architecture-beta`. Probed in the browser (round 12): the
 * beta grammar draws NO service box. Every service is an 80x80 icon plate with
 * its label drawn over the plate's bottom edge, and mermaid breaks the label
 * into `<tspan>` rows before it reaches the DOM — so `retrieval` arrived as
 * `retri / eva / l`, a two-word label wrapped onto the plate, and the whole
 * drawing read as floating glyphs with text over them. Nothing in CSS can
 * repair that, because the split has already happened upstream. `toMermaid`
 * stays (it is the model/doc export and the chat surface's own path) but the
 * visual component draws its own SVG: a box with the label inside it, one small
 * kind glyph, orthogonal hairline connectors, and a boundary whose title sits
 * above its rule instead of on it.
 *
 * POSITIONING IS DECLARED, NOT SOLVED. A spec that carries `col`/`row` on every
 * service (and optionally a rect on a group) is drawn on a fixed grid — no
 * force-directed layout to fight and a stable coordinate frame for the camera
 * walk. A spec without positions falls back to the mermaid render.
 *
 * IDS ARE THE TOUR'S HANDLE. Each box is `arch-service-<id>` and each boundary
 * `arch-group-<id>`, which is exactly what `ArchitectureTour` resolves inside
 * the drawn SVG, so the swap/glow/camera code needed no change when the
 * renderer did.
 */

import type { ArchEdge, ArchGroup, ArchIcon, ArchService, ArchSpec } from "./ArchitectureDiagram";
import { ICONS } from "../logos";

const BOX_W = 176;
const BOX_H = 58;
const GAP_X = 84;
const GAP_Y = 62;
const GROUP_PAD = 18;
const GROUP_HEAD = 46;
const GLYPH = 22;
/** The label column: the text starts after the glyph and its gutter. */
const LABEL_X = 48;
/** Roughly how many characters fit the label column at the label's size. */
const LABEL_MAX_CHARS = 15;

/**
 * Break a service label onto at most two lines so it never runs past its box.
 * A box is `BOX_W` wide and the label column starts at `LABEL_X`, so the budget
 * is ~15 monospace characters; anything longer splits on the first space that
 * balances the two lines, and a single word that still overruns is left to the
 * box's own clip rather than broken mid-word. Returns one line when it fits.
 */
function wrapLabel(label: string): string[] {
  if (label.length <= LABEL_MAX_CHARS) return [label];
  const words = label.split(" ");
  if (words.length === 1) return [label];
  let best: string[] = [label];
  let bestDelta = Infinity;
  for (let cut = 1; cut < words.length; cut += 1) {
    const line1 = words.slice(0, cut).join(" ");
    const line2 = words.slice(cut).join(" ");
    if (line1.length > LABEL_MAX_CHARS || line2.length > LABEL_MAX_CHARS) continue;
    const delta = Math.abs(line1.length - line2.length);
    if (delta < bestDelta) {
      bestDelta = delta;
      best = [line1, line2];
    }
  }
  return best;
}

/** A laid-out service: a spec service that carries a grid slot. */
export type PlacedService = ArchService & { col: number; row: number };
type Rect = { x: number; y: number; w: number; h: number };

export function hasLayout(spec: ArchSpec): spec is ArchSpec & { services: PlacedService[] } {
  return spec.services.length > 0 && spec.services.every((s) => s.col != null && s.row != null);
}

const gx = (col: number): number => col * (BOX_W + GAP_X);
/** Extra lane so a box above a boundary sits clear of its caption rule. */
const ROW_LANE_EXTRA = 34;
const gy = (row: number): number => row * (BOX_H + GAP_Y) + (row >= 1 ? ROW_LANE_EXTRA : 0);

function boxRect(service: PlacedService): Rect {
  return { x: gx(service.col), y: gy(service.row), w: BOX_W, h: BOX_H };
}

function groupRect(group: ArchGroup, services: PlacedService[]): Rect | null {
  if (group.col != null && group.row != null && group.cols != null && group.rows != null) {
    return {
      x: gx(group.col) - GROUP_PAD,
      y: gy(group.row) - GROUP_PAD - (GROUP_HEAD - GROUP_PAD),
      w: (group.cols - 1) * (BOX_W + GAP_X) + BOX_W + GROUP_PAD * 2,
      h: (group.rows - 1) * (BOX_H + GAP_Y) + BOX_H + GROUP_PAD * 2,
    };
  }
  const members = services.filter((s) => s.group === group.id).map(boxRect);
  if (members.length === 0) return null;
  const xs = members.map((r) => r.x);
  const ys = members.map((r) => r.y);
  const xe = members.map((r) => r.x + r.w);
  const ye = members.map((r) => r.y + r.h);
  return {
    x: Math.min(...xs) - GROUP_PAD,
    y: Math.min(...ys) - GROUP_HEAD,
    w: Math.max(...xe) - Math.min(...xs) + GROUP_PAD * 2,
    h: Math.max(...ye) - Math.min(...ys) + GROUP_HEAD + GROUP_PAD,
  };
}

type Routed = { d: string; lx: number; ly: number };

/**
 * Orthogonal connector between two boxes.
 *
 * The label is placed on the LONGEST run of the path and offset perpendicular
 * to it, which is the only position guaranteed clear of both boxes: the elbow
 * band between two rows/columns is often thinner than the label itself, so
 * "midpoint of the elbow" kept landing on a box edge. `sx`/`sy` name the first
 * segment so the caller can offset correctly.
 */
function route(a: Rect, b: Rect): Routed {
  const acx = a.x + a.w / 2;
  const acy = a.y + a.h / 2;
  const bcx = b.x + b.w / 2;
  const bcy = b.y + b.h / 2;
  const OFF = 7;

  // A straight horizontal neighbour: one line, label above it in the gutter.
  if (Math.abs(acy - bcy) < 1 && Math.abs(bcx - acx) >= a.w / 2 + b.w / 2) {
    const rightward = bcx >= acx;
    const sx = rightward ? a.x + a.w : a.x;
    const tx = rightward ? b.x : b.x + b.w;
    return { d: `M${sx} ${acy} H${tx}`, lx: (sx + tx) / 2, ly: acy - OFF };
  }

  if (Math.abs(bcx - acx) >= Math.abs(bcy - acy)) {
    const rightward = bcx >= acx;
    const sx = rightward ? a.x + a.w : a.x;
    const tx = rightward ? b.x : b.x + b.w;
    const mx = (sx + tx) / 2;
    return {
      d: `M${sx} ${acy} H${mx} V${bcy} H${tx}`,
      // The elbow: gutter centre-x, band centre-y. Clear of both boxes.
      lx: mx,
      ly: (acy + bcy) / 2,
    };
  }

  const downward = bcy >= acy;
  const sy = downward ? a.y + a.h : a.y;
  const ty = downward ? b.y : b.y + b.h;
  const my = (sy + ty) / 2;
  return {
    d: `M${acx} ${sy} V${my} H${bcx} V${ty}`,
    lx: acx,
    ly: my - OFF,
  };
}

/** A 22px monoline kind glyph, drawn in a local 20x20 box. A named `logo` slug
 * from the kit registry wins when it resolves (simple-icons paths are 24x24
 * fill shapes, drawn in currentColor like everything else on the box);
 * anything else falls through to the kind glyph, so unmarked vendors degrade
 * to a generic plate instead of an empty one. */
function Glyph({ kind, logo }: { kind?: ArchIcon; logo?: string }) {
  const mark = logo ? ICONS[logo] : undefined;
  if (mark) {
    /* simple-icons paths live in a 24x24 box; scale into the local 20x20 so
       a brand mark fills exactly the frame the kind glyphs use. */
    return (
      <g transform={`scale(${20 / 24})`}>
        <path d={mark.path} fill="currentColor" stroke="none" />
      </g>
    );
  }
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.4, strokeLinecap: "round" as const };
  switch (kind) {
    case "database":
      return (
        <g {...common}>
          <ellipse cx={10} cy={5.5} rx={6} ry={2.4} />
          <path d="M4 5.5v9c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4v-9" />
        </g>
      );
    case "disk":
      return (
        <g {...common}>
          <rect x={4} y={3.5} width={12} height={13} />
          <path d="M7 3.5v6h6v-6" />
          <path d="M7 16.5v-4h6v4" />
        </g>
      );
    case "cloud":
      return (
        <g {...common}>
          <path d="M6 14.5h9a3.2 3.2 0 0 0 .3-6.4 4.6 4.6 0 0 0-8.9-1.1A3.4 3.4 0 0 0 6 14.5Z" />
        </g>
      );
    case "server":
      return (
        <g {...common}>
          <rect x={3.5} y={4} width={13} height={5} />
          <rect x={3.5} y={11} width={13} height={5} />
          <path d="M6.2 6.5h.01M6.2 13.5h.01" />
        </g>
      );
    default:
      return (
        <g {...common}>
          <circle cx={10} cy={10} r={6.2} />
          <path d="M3.8 10h12.4" />
          <ellipse cx={10} cy={10} rx={3} ry={6.2} />
        </g>
      );
  }
}

export type ArchitectureSvgProps = {
  spec: ArchSpec;
  /** Service and group ids to mark as the current step. */
  lit?: readonly string[];
  className?: string;
};

export function ArchitectureSvg({ spec, lit, className }: ArchitectureSvgProps) {
  if (!hasLayout(spec)) return null;
  const services: PlacedService[] = spec.services;
  const on = new Set(lit ?? []);
  const byId = new Map(services.map((s) => [s.id, s]));
  const rects = new Map(services.map((s) => [s.id, boxRect(s)]));
  const groups = (spec.groups ?? [])
    .map((g) => ({ group: g, rect: groupRect(g, services) }))
    .filter((g): g is { group: ArchGroup; rect: Rect } => g.rect !== null);
  const edges: Array<{ edge: ArchEdge; routed: Routed }> = [];
  for (const edge of spec.edges) {
    const a = rects.get(edge.from);
    const b = rects.get(edge.to);
    if (a && b && byId.has(edge.from) && byId.has(edge.to)) {
      edges.push({ edge, routed: route(a, b) });
    }
  }

  const boxes = services.map(boxRect);
  const minX = Math.min(...boxes.map((r) => r.x), ...groups.map((g) => g.rect.x));
  const maxX = Math.max(...boxes.map((r) => r.x + r.w), ...groups.map((g) => g.rect.x + g.rect.w));
  const minY = Math.min(...boxes.map((r) => r.y), ...groups.map((g) => g.rect.y - 24));
  const maxY = Math.max(...boxes.map((r) => r.y + r.h), ...groups.map((g) => g.rect.y + g.rect.h));
  const pad = 26;
  const viewBox = `${minX - pad} ${minY - pad} ${maxX - minX + pad * 2} ${maxY - minY + pad * 2}`;

  const uid = spec.title.replace(/[^a-zA-Z0-9]/g, "");
  const markerId = `arch-arrow-${uid}`;
  // Keep a label off the target box: sit it a quarter of the way along the run.


  return (
    <svg
      className={["arch-svg", className ?? ""].filter(Boolean).join(" ")}
      viewBox={viewBox}
      role="img"
      aria-label={`${spec.title}. ${spec.description}`}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <marker id={markerId} viewBox="0 0 8 8" refX={7} refY={4} markerWidth={9} markerHeight={9} orient="auto">
          <path className="arch-arrow" d="M0 0.6 L7 4 L0 7.4" />
        </marker>
      </defs>

      {groups.map(({ group, rect }) => (
        <g
          key={group.id}
          id={`arch-group-${group.id}`}
          className={`arch-group${on.has(group.id) ? " is-on" : ""}`}
        >
          <rect className="arch-group__box" x={rect.x} y={rect.y} width={rect.w} height={rect.h} />
          <text className="arch-group__label" x={rect.x} y={rect.y + 24}>
            {group.label}
          </text>
        </g>
      ))}

      {edges.map(({ edge, routed }) => (
        <g key={`${edge.from}-${edge.to}`} className={`arch-edge${on.has(edge.from) && on.has(edge.to) ? " is-on" : ""}`}>
          <path
            className="arch-edge__line"
            d={routed.d}
            markerEnd={edge.arrow === "from" || edge.arrow === "none" ? undefined : `url(#${markerId})`}
            markerStart={edge.arrow === "from" ? `url(#${markerId})` : undefined}
          />
          {edge.label ? (
            <text className="arch-edge__label" x={routed.lx} y={routed.ly - 4}>
              {edge.label}
            </text>
          ) : null}
        </g>
      ))}

      {services.map((service) => {
        const r = rects.get(service.id) as Rect;
        return (
          <g
            key={service.id}
            id={`arch-service-${service.id}`}
            className={`arch-node${on.has(service.id) ? " is-on" : ""}`}
          >
            <rect className="arch-node__box" x={r.x} y={r.y} width={r.w} height={r.h} />
            <g className="arch-node__glyph" transform={`translate(${r.x + 14} ${r.y + (BOX_H - GLYPH) / 2}) scale(${GLYPH / 20})`}>
              <Glyph kind={service.icon} logo={service.logo} />
            </g>
            <text className="arch-node__label" x={r.x + LABEL_X} y={r.y + BOX_H / 2} dominantBaseline="middle">
              {(() => {
                const lines = wrapLabel(service.label);
                if (lines.length === 1) return lines[0];
                return lines.map((line, i) => (
                  <tspan key={line} x={r.x + LABEL_X} dy={i === 0 ? -6 : 13}>
                    {line}
                  </tspan>
                ));
              })()}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
