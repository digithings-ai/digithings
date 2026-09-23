"use client";

import {
  NODE_H,
  NODE_W,
  OWNED_GRAPH,
  RENTED_GRAPH,
  VIEW,
  type ArchGraph,
} from "@/lib/whyStack";

/**
 * The two architecture diagrams (round 9c, #4429).
 *
 * ONE grammar, drawn twice. The owner: "i want a visual like a graph like a
 * design document or a design graph an architecture graph this is a visual graph
 * with nodes and lines connecting the different services from a database to a
 * cloud infrastructure the specific graph that you typically build when you're
 * designing a system or an architecture … compare what that looks like for the
 * conventional off-the-shelf solution versus what that would look like for digi
 * things if you were to use all the digi things modules".
 *
 * So this is a system-design diagram, not a slide: squared boxes, hairline
 * connectors, mono labels, the same frame on both sides so the two views diff at
 * a glance. No vendor is named on the conventional side — only the generic parts
 * an engineer would draw — and no invoice, no figure, no percentage appears on
 * either side.
 *
 * The diagram assembles as the walker advances: a box appears when its step
 * lights it, and a connector is drawn only once BOTH of its ends exist, which is
 * how an architecture sketch is actually built up.
 */
function ArchDiagram({ graph, lit }: { graph: ArchGraph; lit: string[] }) {
  const on = (id: string) => lit.includes(id);
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));

  return (
    <svg
      className="whyx-graph"
      viewBox={`0 0 ${VIEW.w} ${VIEW.h}`}
      role="img"
      aria-label={graph.aria}
      preserveAspectRatio="xMidYMid meet"
    >
      <rect
        className="whyx-graph__boundary"
        x={graph.boundary.x}
        y={graph.boundary.y}
        width={graph.boundary.w}
        height={graph.boundary.h}
      />
      <text className="whyx-graph__boundary-label" x={graph.boundary.x + 8} y={graph.boundary.y - 10}>
        {graph.boundary.label}
      </text>

      <g className="whyx-graph__edges">
        {graph.edges.map((edge) => {
          const a = nodeById.get(edge.a);
          const b = nodeById.get(edge.b);
          if (!a || !b) return null;
          const live = on(edge.a) && on(edge.b);
          return (
            <line
              key={`${edge.a}-${edge.b}`}
              className={`whyx-graph__edge${live ? " is-on" : ""}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
            />
          );
        })}
      </g>

      <g className="whyx-graph__nodes">
        {graph.nodes.map((node) => {
          const live = on(node.id);
          return (
            <g
              key={node.id}
              className={`whyx-graph__node${live ? " is-on" : ""}`}
              data-kind={node.kind}
            >
              <rect
                x={node.x - NODE_W / 2}
                y={node.y - NODE_H / 2}
                width={NODE_W}
                height={NODE_H}
              />
              <text x={node.x} y={node.y + 4}>
                {node.label}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}

/** The conventional stack, assembling as its steps light. */
export function RentedArch({ lit }: { lit: string[] }) {
  return (
    <div className="whyx-view" data-side="rented">
      <p className="whyx-view__caption">the conventional stack, off the shelf</p>
      <ArchDiagram graph={RENTED_GRAPH} lit={lit} />
      <p className="whyx-view__foot">
        one boundary, one account, one release schedule — the surface is the app, and nothing behind
        it is a seam you can move
      </p>
    </div>
  );
}

/**
 * The same system, built from the modules. Identical frame and connectors; the
 * boxes are processes you run and the boundary is your own.
 */
export function OwnedArch({ lit }: { lit: string[] }) {
  return (
    <div className="whyx-view" data-side="owned">
      <p className="whyx-view__caption">the same system, every layer a module you run</p>
      <ArchDiagram graph={OWNED_GRAPH} lit={lit} />
      <p className="whyx-view__foot">
        the same shape with the seams exposed — each module is yours to swap, host and build on,
        and no module assumes you run any other
      </p>
    </div>
  );
}
