/**
 * The convergence diagram (canon §11): services flow into the supervisor,
 * the supervisor flows into the surfaces. Every path wears its module's
 * livery as an identifier — the one color allowed on the umbrella — and the
 * flagship (digiquant) runs brightest; digivault stays a bare hairline (its
 * livery is unassigned). Pure SVG, server-rendered, no client JS: the
 * draw-in is CSS scroll-scrubbed (`animation-timeline: view()` in
 * globals.css, @supports-gated); reduced-motion or no support renders the
 * diagram fully drawn (law 06).
 */
export function Convergence() {
  return (
    <div className="dtconv">
      <svg
        viewBox="0 0 720 290"
        role="img"
        aria-label="Seven services — digiquant, digisearch, digismith, digivault, digikey, digiclaw, digibase — converge into digigraph, the supervisor, which serves Olympus and DigiChat."
      >
        <g className="dtconv-labels-in">
          <text x="16" y="34">digiquant <tspan className="dim">:8001</tspan></text>
          <text x="16" y="69">digisearch <tspan className="dim">:8002</tspan></text>
          <text x="16" y="104">digismith <tspan className="dim">:8003</tspan></text>
          <text x="16" y="139">digivault <tspan className="dim">:8004</tspan></text>
          <text x="16" y="174">digikey <tspan className="dim">:8005</tspan></text>
          <text x="16" y="209">digiclaw <tspan className="dim">· heartbeat</tspan></text>
          <text x="16" y="244">digibase <tspan className="dim">· shared lib</tspan></text>
        </g>
        <g className="dtconv-paths" fill="none">
          <path className="dtconv-p p-digiquant" pathLength={1} d="M150,30 C 220,30 235,135 300,135" />
          <path className="dtconv-p p-digisearch" pathLength={1} d="M150,65 C 220,65 235,135 300,135" />
          <path className="dtconv-p p-digismith" pathLength={1} d="M150,100 C 220,100 235,135 300,135" />
          <path className="dtconv-p p-hairline" pathLength={1} d="M150,135 C 220,135 235,135 300,135" />
          <path className="dtconv-p p-digikey" pathLength={1} d="M150,170 C 220,170 235,135 300,135" />
          <path className="dtconv-p p-digiclaw" pathLength={1} d="M150,205 C 220,205 235,135 300,135" />
          <path className="dtconv-p p-digibase" pathLength={1} d="M150,240 C 220,240 235,135 300,135" />
          <path className="dtconv-p dtconv-out p-hairline" pathLength={1} d="M440,135 C 500,135 510,95 558,95" />
          <path className="dtconv-p dtconv-out p-digichat" pathLength={1} d="M440,135 C 500,135 510,175 558,175" />
        </g>
        <g className="dtconv-node">
          <rect x="300" y="112" width="140" height="46" rx="8" />
          <text x="370" y="131" textAnchor="middle" className="name">digigraph</text>
          <text x="370" y="147" textAnchor="middle" className="sub">:8000 · supervisor</text>
        </g>
        <g className="dtconv-labels-out">
          <text x="566" y="99">olympus <tspan className="dim">· dashboard</tspan></text>
          <text x="566" y="179">digichat <tspan className="dim">:3005</tspan></text>
        </g>
      </svg>
    </div>
  );
}
