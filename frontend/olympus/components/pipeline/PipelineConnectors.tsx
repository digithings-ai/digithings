import type { Connector, LaidOutNode } from '@/lib/pipeline-layout';

interface PipelineConnectorsProps {
  connectors: Connector[];
  nodes: LaidOutNode[];
  width: number;
  height: number;
}

function nodeById(nodes: LaidOutNode[], id: string): LaidOutNode | undefined {
  return nodes.find((n) => n.id === id);
}

/** Generate a clean cubic-bezier SVG path between two nodes. */
function buildPath(from: LaidOutNode, to: LaidOutNode): string {
  // Determine connection points
  const fromRight = from.x + from.width;
  const fromMidY = from.y + from.height / 2;
  const toLeft = to.x;
  const toMidY = to.y + to.height / 2;

  // Vertical branch (fanout): connect bottom center of parent to top center of child
  if (from.x === to.x && to.y > from.y) {
    const fx = from.x + from.width / 2;
    const fy = from.y + from.height;
    const tx = to.x + to.width / 2;
    const ty = to.y;
    const cy = (fy + ty) / 2;
    return `M ${fx} ${fy} C ${fx} ${cy}, ${tx} ${cy}, ${tx} ${ty}`;
  }

  // Horizontal connection: right edge of from → left edge of to
  const cpOffset = Math.max(20, (toLeft - fromRight) * 0.45);
  return `M ${fromRight} ${fromMidY} C ${fromRight + cpOffset} ${fromMidY}, ${toLeft - cpOffset} ${toMidY}, ${toLeft} ${toMidY}`;
}

export default function PipelineConnectors({
  connectors,
  nodes,
  width,
  height,
}: PipelineConnectorsProps) {
  return (
    <svg
      aria-hidden="true"
      className="absolute inset-0 pointer-events-none overflow-visible"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
    >
      {/* Default (calm) connectors first … */}
      {connectors.map((conn) => {
        if (conn.active) return null;
        const from = nodeById(nodes, conn.fromId);
        const to = nodeById(nodes, conn.toId);
        if (!from || !to) return null;
        return (
          <path
            key={`${conn.fromId}→${conn.toId}`}
            d={buildPath(from, to)}
            stroke="var(--color-border-subtle)"
            strokeOpacity="0.9"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        );
      })}
      {/* … active (cyan) connectors after, so they read on top. */}
      {connectors.map((conn) => {
        if (!conn.active) return null;
        const from = nodeById(nodes, conn.fromId);
        const to = nodeById(nodes, conn.toId);
        if (!from || !to) return null;
        return (
          <path
            key={`active:${conn.fromId}→${conn.toId}`}
            d={buildPath(from, to)}
            stroke="var(--color-fin-blue)"
            strokeOpacity="0.55"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        );
      })}
    </svg>
  );
}
