/**
 * Arc-flight routing map — mined from revolut.com's globe (money crossing
 * borders), in our register: orders routing across venues. An abstract
 * graticule with venue nodes and great-circle-ish arcs; a bright packet flows
 * along each arc (a normalized stroke-dash that travels the path), and the
 * nodes ping. Pure SVG + CSS animation, so a plain server component; the
 * accent dresses it (re-themes with the livery), and reduced motion holds it
 * still. Not a real map — an evocative one.
 */
type Node = { id: string; label: string; x: number; y: number };

const W = 800;
const H = 380;

const NODES: Node[] = [
  { id: "coinbase", label: "coinbase", x: 150, y: 150 },
  { id: "cme", label: "cme", x: 205, y: 178 },
  { id: "nyse", label: "nyse", x: 250, y: 145 },
  { id: "lse", label: "lse", x: 415, y: 120 },
  { id: "binance", label: "binance", x: 615, y: 170 },
  { id: "okx", label: "okx", x: 665, y: 200 },
];

const LINKS: [string, string][] = [
  ["coinbase", "nyse"],
  ["cme", "nyse"],
  ["nyse", "lse"],
  ["lse", "binance"],
  ["binance", "okx"],
  ["coinbase", "binance"],
];

const byId = (id: string) => NODES.find((n) => n.id === id)!;

function arc(a: Node, b: Node) {
  const dist = Math.hypot(b.x - a.x, b.y - a.y);
  const lift = Math.min(150, dist * 0.42);
  const cx = (a.x + b.x) / 2;
  const cy = Math.min(a.y, b.y) - lift;
  return `M${a.x} ${a.y} Q${cx} ${cy} ${b.x} ${b.y}`;
}

export function RoutingMap() {
  const arcs = LINKS.map(([f, t]) => ({ id: `${f}-${t}`, d: arc(byId(f), byId(t)) }));

  return (
    // The static frame (spacing + border/surface) migrates to token-backed
    // Tailwind utilities via the @theme bridge; bg-surface/40 emits the same
    // color-mix. Every rm-* SVG child rule (strokes, animated dash, ping ring)
    // stays in effects.css — that's the genuine animation mechanics.
    <svg
      className="mt-[1.6rem] w-full h-auto rounded-[14px] border border-hair bg-surface/40"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Orders routing across trading venues"
    >
      {/* graticule — faint latitude/longitude lines suggesting a map */}
      <g className="rm-grid" aria-hidden="true">
        {Array.from({ length: 7 }, (_, i) => (
          <line key={`h${i}`} x1="0" x2={W} y1={(i + 1) * (H / 8)} y2={(i + 1) * (H / 8)} />
        ))}
        {Array.from({ length: 9 }, (_, i) => (
          <line key={`v${i}`} x1={(i + 1) * (W / 10)} x2={(i + 1) * (W / 10)} y1="0" y2={H} />
        ))}
      </g>

      {/* base arcs + flowing packets */}
      {arcs.map((a, i) => (
        <g key={a.id}>
          <path className="rm-arc-base" d={a.d} />
          <path
            className="rm-arc-flow"
            d={a.d}
            pathLength={1}
            style={{ animationDelay: `${i * 0.5}s` }}
          />
        </g>
      ))}

      {/* venue nodes: ping ring + dot + label */}
      {NODES.map((n, i) => (
        <g key={n.id} className="rm-node-g">
          <circle
            className="rm-ring"
            cx={n.x}
            cy={n.y}
            r="5"
            style={{ animationDelay: `${i * 0.4}s` }}
          />
          <circle className="rm-node" cx={n.x} cy={n.y} r="3.5" />
          <text className="rm-label" x={n.x} y={n.y - 12} textAnchor="middle">
            {n.label}
          </text>
        </g>
      ))}
    </svg>
  );
}
