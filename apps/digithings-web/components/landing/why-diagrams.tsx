"use client";

/**
 * The SVG diagrams for the `#why` variations (`/variants/why`, #4429 round 8).
 *
 * The owner asked to "show this animation to try to show this evolution …
 * Maybe we have kind of a UML or a design graph of what a managed platform looks
 * like versus digithings … we kind of show the managed platform first and then we
 * show all the digithings improvements of how it kind of changes the managed
 * platform and turns it into a fully modular, customizable infrastructure that
 * you actually own".
 *
 * All three diagrams draw the SAME seven layers — the ones the live band already
 * argues about (`Argument.tsx`'s `LAYERS`): weights, index, tools, runtime, keys,
 * log, metal. In every diagram the left/stacked state is a single bounded whole
 * and the right/spread state is the same seven things detached, each with a seam
 * you can move. Nothing here names a vendor and nothing states a price: the
 * diagram shows the SHAPE of the two arrangements, which is the whole argument.
 *
 * Movement is driven entirely by the parent's `--why-p` (0 → 1) custom property,
 * written once per frame by the scroll handler in `WhyVariants.tsx`. Each part
 * carries its two positions as `--x0/--y0` and `--x1/--y1`; the transform that
 * interpolates them lives in `app/globals.css`, so no React state ticks.
 */

/** The seven layers, with both of their positions. */
type WhyPart = {
  id: string;
  /** The label inside the slab. */
  label: string;
  /** What you get back once it is a seam you own. */
  seam: string;
  /** Index in the stack (top to bottom). */
  slot: number;
  /** Where the part sits once detached. */
  gx: number;
  gy: number;
};

export const WHY_PARTS: WhyPart[] = [
  { id: "models", label: "weights", seam: "swap the model", slot: 0, gx: 150, gy: 102 },
  { id: "retrieval", label: "index", seam: "own the index", slot: 1, gx: 150, gy: 262 },
  { id: "tools", label: "tools", seam: "run the tools", slot: 2, gx: 150, gy: 422 },
  { id: "graph", label: "runtime", seam: "host the graph", slot: 3, gx: 460, gy: 262 },
  { id: "keys", label: "keys", seam: "issue the keys", slot: 4, gx: 770, gy: 102 },
  { id: "audit", label: "log", seam: "keep the log", slot: 5, gx: 770, gy: 262 },
  { id: "hosts", label: "metal", seam: "choose the metal", slot: 6, gx: 770, gy: 422 },
];

/** The slab's own geometry, shared by both states. */
const SLAB_W = 200;
const SLAB_H = 52;
/** The stack: first slot's top, and the step between slots. */
const STACK_X = 360;
const STACK_Y = 54;
const STACK_STEP = 58;

/** Where a part sits while it is still inside the monolith. */
function stackPos(slot: number): { x: number; y: number } {
  return { x: STACK_X, y: STACK_Y + slot * STACK_STEP };
}

/** Where a part sits once detached. */
function graphPos(part: WhyPart): { x: number; y: number } {
  return { x: part.gx - SLAB_W / 2, y: part.gy - SLAB_H / 2 };
}

/**
 * One slab. Both positions are handed to CSS so the interpolation happens in one
 * compositor-friendly transform per part.
 */
function Part({
  part,
  showSeam,
}: {
  part: WhyPart;
  showSeam: boolean;
}) {
  const from = stackPos(part.slot);
  const to = graphPos(part);
  return (
    <g
      className="why-part"
      style={
        {
          "--x0": `${from.x}px`,
          "--y0": `${from.y}px`,
          "--x1": `${to.x}px`,
          "--y1": `${to.y}px`,
        } as React.CSSProperties
      }
    >
      <rect className="why-part__slab" width={SLAB_W} height={SLAB_H} rx={4} />
      <text className="why-part__label" x={14} y={SLAB_H / 2 + 4}>
        {part.label}
      </text>
      {showSeam ? (
        <text className="why-part__seam" x={SLAB_W / 2} y={SLAB_H + 22} textAnchor="middle">
          {part.seam}
        </text>
      ) : null}
    </g>
  );
}

/**
 * V2 — the monolith that comes apart into the graph.
 *
 * State A: one bounded whole, one account badge, the seven layers stacked
 * inside it. State B: the same seven, spread out, each with its seam named, and
 * edges to the runtime that now sit in YOUR network.
 */
export function MonolithToGraph({ withSeams = true }: { withSeams?: boolean }) {
  const hub = WHY_PARTS.find((p) => p.id === "graph")!;
  return (
    <svg
      className="why-diagram why-diagram--morph"
      viewBox="0 0 920 520"
      role="img"
      aria-label="Seven stacked layers inside one boundary come apart into seven detachable nodes with named seams"
      preserveAspectRatio="xMidYMid meet"
    >
      {/* The single perimeter — the thing you are outside of. Fades as the
          layers detach. */}
      <rect className="why-morph__boundary" x={336} y={42} width={248} height={432} rx={16} />
      <text className="why-morph__account" x={460} y={28} textAnchor="middle">
        one account · one bill
      </text>

      {/* The seams the parts travel to. Drawn under the parts. */}
      <g className="why-morph__edges">
        {WHY_PARTS.filter((p) => p.id !== hub.id).map((part) => (
          <line
            key={part.id}
            x1={hub.gx}
            y1={hub.gy}
            x2={part.gx}
            y2={part.gy}
          />
        ))}
      </g>

      {WHY_PARTS.map((part) => (
        <Part key={part.id} part={part} showSeam={withSeams} />
      ))}
    </svg>
  );
}

/**
 * V3 — the exploded layer stack.
 *
 * The same seven slabs, flush behind one boundary, separating on scroll. The
 * least machinery of the four: the only thing moving is the vertical spread, and
 * each slab grows its seam label as the gap opens.
 */
export function LayerExplode() {
  return (
    <svg
      className="why-diagram why-diagram--explode"
      viewBox="0 0 920 560"
      role="img"
      aria-label="Seven stacked layers separate, each naming the seam you get back"
      preserveAspectRatio="xMidYMid meet"
    >
      <rect className="why-explode__boundary" x={300} y={30} width={320} height={480} rx={16} />
      <text className="why-explode__account" x={460} y={20} textAnchor="middle">
        one boundary, one release schedule
      </text>
      {WHY_PARTS.map((part) => (
        <g
          key={part.id}
          className="why-explode__row"
          style={{ "--i": part.slot } as React.CSSProperties}
        >
          <rect className="why-explode__slab" x={320} y={60 + part.slot * 54} width={280} height={44} rx={3} />
          <text className="why-explode__label" x={336} y={60 + part.slot * 54 + 28}>
            {part.label}
          </text>
          <text className="why-explode__seam" x={586} y={60 + part.slot * 54 + 28} textAnchor="end">
            {part.seam}
          </text>
        </g>
      ))}
    </svg>
  );
}

/**
 * V4 — one frame of the three-state evolution, drawn from the same parts.
 *
 * `frame` 1 is the monolith, 2 the detached seven, 3 the detached seven with
 * your own providers and an app of yours on top. The three are rendered as one
 * animated diagram by stacking frames and cross-fading them on `--why-p`, so the
 * three states are literally the same drawing at three points in time.
 */
export function EvolutionGraph({ frame }: { frame: 1 | 2 | 3 }) {
  const spread = frame !== 1;
  const hub = WHY_PARTS.find((p) => p.id === "graph")!;
  return (
    <svg
      className="why-diagram why-diagram--evolution"
      viewBox="0 0 920 520"
      role="img"
      aria-label={
        frame === 1
          ? "One vendor's stack: seven layers inside a single boundary"
          : frame === 2
            ? "The same seven layers, each a seam you can move"
            : "The same seven layers on your own providers, with your own app on top"
      }
      preserveAspectRatio="xMidYMid meet"
    >
      {frame === 1 ? (
        <>
          <rect className="why-evo__boundary" x={336} y={42} width={248} height={432} rx={16} />
          <text className="why-evo__badge" x={460} y={28} textAnchor="middle">
            one account · one bill · one release schedule
          </text>
        </>
      ) : (
        <g className="why-evo__edges">
          {WHY_PARTS.filter((p) => p.id !== hub.id).map((part) => (
            <line key={part.id} x1={hub.gx} y1={hub.gy} x2={part.gx} y2={part.gy} />
          ))}
        </g>
      )}

      {WHY_PARTS.map((part) => {
        const pos = spread ? graphPos(part) : stackPos(part.slot);
        return (
          <g
            key={part.id}
            className="why-evo__part"
            style={{ transform: `translate(${pos.x}px, ${pos.y}px)` } as React.CSSProperties}
          >
            <rect className="why-part__slab" width={SLAB_W} height={SLAB_H} rx={4} />
            <text className="why-part__label" x={14} y={SLAB_H / 2 + 4}>
              {part.label}
            </text>
            {frame === 2 ? (
              <text className="why-part__seam" x={SLAB_W / 2} y={SLAB_H + 22} textAnchor="middle">
                {part.seam}
              </text>
            ) : null}
            {frame === 3 ? (
              <text className="why-part__seam" x={SLAB_W / 2} y={SLAB_H + 22} textAnchor="middle">
                yours
              </text>
            ) : null}
          </g>
        );
      })}

      {frame === 3 ? (
        <g className="why-evo__app">
          <rect x={330} y={196} width={260} height={128} rx={8} />
          <text x={460} y={252} textAnchor="middle">
            your app
          </text>
          <text className="why-evo__app-sub" x={460} y={276} textAnchor="middle">
            REST · MCP · CLI · container
          </text>
        </g>
      ) : null}
    </svg>
  );
}
