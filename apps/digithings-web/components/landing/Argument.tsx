"use client";

import { CtaLink } from "@digithings/ui";

/**
 * The argument — a seam diagram (v15 Stage 5, #4429).
 *
 * Owner direction, point 10: "'Why digithings' more creatively built out — a
 * visual explanation, not a long sequential readout."
 *
 * So the section no longer walks a numbered spine through paragraphs. It draws
 * the same seven layers of the stack TWICE, side by side — once on the managed
 * platform, once on yours — and marks each one as a seam. The argument is the
 * picture: every layer is either theirs or yours, and on the right every one of
 * them moves by config. Three glanceable nodes below carry the three claims in
 * one line each. The old `ArgumentProse` / `ArgumentStages` / `ArgumentContrast`
 * / `ArgumentGlyphs` exports are retired with this change — a seven-row prose
 * table and a paragraph column were the "long sequential readout" the note
 * objected to.
 *
 * Honesty constraints, unchanged and non-negotiable:
 *  - Never claim open models *surpassed* frontier flagships. "At par or close"
 *    is the strongest claim the evidence supports, and it is the wording used.
 *  - Named platforms are described by their public positioning (managed
 *    surface, seats, proprietary weights, hosted tooling) — nothing is asserted
 *    about their unpublished pricing or contract terms. We do not name them in
 *    the diagram at all; the left column is the *shape*, not an accusation.
 *  - No performance figures, no backtest or in-sample wording, no promise of
 *    live trading.
 */

type Layer = {
  /** The layer's name — one word where possible. */
  layer: string;
  /** What the managed platform owns. */
  theirs: string;
  /** What you own instead. */
  yours: string;
};

// Seven layers, top to bottom, from weights down to metal. Every row is a seam
// — there is deliberately no row that is *not* swappable, because that is the
// whole claim. Keep each cell to a fragment: the diagram's job is the shape,
// and a sentence here would put the paragraph back.
const LAYERS: Layer[] = [
  {
    layer: "models",
    theirs: "their weights, their release schedule",
    yours: "any provider behind one interface",
  },
  {
    layer: "retrieval",
    theirs: "their index, billed per vector",
    yours: "digisearch over a store you choose",
  },
  { layer: "tools", theirs: "their tool registry", yours: "MCP servers you run" },
  { layer: "graph", theirs: "their hosted runtime", yours: "digigraph on your hosts" },
  { layer: "keys", theirs: "their account and rate limits", yours: "digikey — your keys, your scopes" },
  {
    layer: "audit",
    theirs: "their logs, their retention",
    yours: "digismith — append-only, on your disk",
  },
  { layer: "hosts", theirs: "their cloud, in their regions", yours: "your machine, VM or cluster" },
];

const GRID = "grid grid-cols-[minmax(0,1fr)_3.4rem_minmax(0,1fr)]";

/** The diagram: the same seven layers drawn twice, every one a seam. */
export function ArgumentSeams() {
  return (
    <div className="w-full max-w-[var(--frame-w)] border border-hair bg-surface">
      <div className={`${GRID} border-b border-hair`}>
        <p className="m-0 px-[1rem] py-[0.7rem] font-mono text-[0.62rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
          the managed platform
        </p>
        <span aria-hidden="true" />
        <p className="m-0 px-[1rem] py-[0.7rem] font-mono text-[0.62rem] uppercase tracking-[var(--tracking-meta)] text-ink">
          digithings
        </p>
      </div>

      {LAYERS.map((l) => (
        <div key={l.layer} className={`${GRID} items-stretch border-b border-hair last:border-b-0`}>
          {/* Theirs — a hollow cell: a hairline rule, transparent ground, muted
              copy. Nothing of yours is in here, and it should look like it. */}
          <div className="flex flex-col gap-[0.12rem] border-s-[3px] border-s-hair px-[1rem] py-[0.62rem]">
            <span className="font-mono text-[0.6rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
              {l.layer}
            </span>
            <span className="text-[0.82rem] leading-[1.5] text-ink-mute">{l.theirs}</span>
          </div>

          {/* The seam itself — the one glyph carrying the argument.
              It was the faintest thing in the diagram (a 7.7px glyph at
              --ink-soft over a 9% dashed rule), which is backwards: the seam is
              the claim. The rule steps up to --ink-mute and the glyph to full
              ink at 1.15rem, so the perforation and the swap both read at a
              glance. The rule stays a 1px hairline so it cannot compete with
              the right column's 3px solid ink edge — the diagram still has one
              loudest line, and it is the owned side's. */}
          <div className="relative flex items-center justify-center" aria-hidden="true">
            <span className="absolute inset-y-0 start-1/2 w-px border-s border-dashed border-ink-mute" />
            <span className="relative font-mono text-[1.15rem] leading-none text-ink">&#8644;</span>
          </div>

          {/* Yours — the same cell, owned. The page's accent is deliberately
              monochrome (globals.css collapses --accent to --ink), so ownership
              is carried by ground + a solid rule + ink copy, never by a hue. */}
          <div className="flex flex-col gap-[0.12rem] border-s-[3px] border-s-ink bg-surface-2 px-[1rem] py-[0.62rem]">
            <span className="font-mono text-[0.6rem] uppercase tracking-[var(--tracking-meta)] text-ink">
              {l.layer}
            </span>
            <span className="text-[0.82rem] leading-[1.5] text-ink">{l.yours}</span>
          </div>
        </div>
      ))}

      <p className="m-0 border-t border-hair px-[1rem] py-[0.7rem] font-mono text-[0.68rem] text-ink-mute">
        the same seven layers, drawn twice. on the right, every one of them is a seam you can move
        — provider, store, tool registry, runtime, keys, log and host.
      </p>
    </div>
  );
}

type Claim = { num: string; label: string; note: string };

// Three claims, one line each. The note is a fragment, not a mechanism
// sentence — anything longer and this becomes the readout again.
const CLAIMS: Claim[] = [
  {
    num: "01",
    label: "the model is not the moat",
    note: "open-weight models sit at par or close on most applied work",
  },
  {
    num: "02",
    label: "the application is the moat",
    note: "retrieval, tools, graph and audit are where the advantage compounds",
  },
  {
    num: "03",
    label: "so every seam is a config change",
    note: "moved on your schedule, not on a vendor's release calendar",
  },
];

/** The three claims, glanceable in one row rather than read as a sequence. */
export function ArgumentClaims() {
  return (
    <div className="grid w-full max-w-[var(--frame-w)] gap-px border border-hair bg-hair min-[860px]:grid-cols-3">
      {CLAIMS.map((c) => (
        <div key={c.num} className="flex flex-col gap-[0.4rem] bg-surface p-[1.2rem]">
          <span className="font-mono text-[0.66rem] tracking-[var(--tracking-meta)] text-ink-mute">
            {c.num}
          </span>
          <span className="font-mono text-[0.92rem] leading-[1.35] text-ink">{c.label}</span>
          <span className="text-[0.84rem] leading-[1.6] text-ink-mute">{c.note}</span>
        </div>
      ))}
    </div>
  );
}

export function ArgumentCta() {
  return (
    <div className="flex flex-wrap items-center gap-[1rem]">
      <CtaLink href="/docs">Read the docs</CtaLink>
      <CtaLink href="/security" variant="ghost">
        How key custody works
      </CtaLink>
    </div>
  );
}
