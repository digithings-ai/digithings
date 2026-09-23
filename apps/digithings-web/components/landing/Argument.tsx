"use client";

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

// Type scale for the diagram's labels, which used to sit below the page's own
// floor: the column headers were 0.62rem (9.92px) and the layer names 0.6rem
// (9.6px), while every other micro-caps label on this page is `--type-meta`
// (12px) and the repo primitives' smallest is 0.68rem (10.88px). Two steps now,
// so the headers read as headers: headers `--type-meta`, row labels 0.68rem.
// Nothing here goes below the page's smallest established size.

/** The diagram: the same seven layers drawn twice, every one a seam. */
export function ArgumentSeams() {
  return (
    <div className="w-full max-w-[var(--frame-w)] border border-hair bg-surface">
      <div className={`${GRID} border-b border-hair`}>
        <p className="m-0 px-[1rem] py-[0.7rem] font-mono text-[length:var(--type-meta)] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
          the managed platform
        </p>
        <span aria-hidden="true" />
        <p className="m-0 px-[1rem] py-[0.7rem] font-mono text-[length:var(--type-meta)] uppercase tracking-[var(--tracking-meta)] text-ink">
          digithings
        </p>
      </div>

      {LAYERS.map((l) => (
        <div key={l.layer} className={`${GRID} items-stretch border-b border-hair last:border-b-0`}>
          {/* Theirs — a hollow cell: a hairline rule, transparent ground, muted
              copy. Nothing of yours is in here, and it should look like it. */}
          <div className="flex flex-col gap-[0.12rem] border-s-[3px] border-s-hair px-[1rem] py-[0.62rem]">
            <span className="font-mono text-[0.68rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
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
            <span className="font-mono text-[0.68rem] uppercase tracking-[var(--tracking-meta)] text-ink">
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

type Claim = { num: string; label: string; note: string; };

/**
 * Three claims. Owner's note this round: "the one two three — the model is not
 * the moat, the application is the moat, so every seam is a config change — you
 * just work on that presentation and the wording, not sure I quite agree with
 * the way it's being presented."
 *
 * What changed and why:
 *
 *  - The three were a *chain* dressed as a list ("so every seam is…"), which
 *    made the third read as a consequence of the first two rather than as the
 *    thing you actually do. They are three independent observations now: what
 *    is commoditised, where the value sits, and how little it costs you to act
 *    on it. Nothing depends on anything else.
 *  - "the moat" twice in a row was a slogan pair. The first claim is stated as
 *    the fact it is (any capable model is available to everyone), and the
 *    second as the consequence (the advantage is the wiring around it) — so the
 *    pair says something instead of rhyming.
 *  - Each note now names a *consequence the reader can check*, not a restatement
 *    of its own label. "the model is not the moat / open-weight models sit at
 *    par or close" told you the same thing twice; the note now says what that
 *    buys you.
 *
 * The honesty ceiling is unchanged: "at par or close" on most applied work is
 * the strongest claim the evidence supports, and open models are never said to
 * have surpassed the frontier flagships.
 */
const CLAIMS: Claim[] = [
  {
    num: "01",
    label: "a capable model is available to everyone",
    note: "open-weight models sit at par or close on most applied work — so renting one is a choice, not a requirement",
  },
  {
    num: "02",
    label: "so the advantage is in the wiring",
    note: "retrieval, tools, the graph and the audit trail are what a competitor cannot copy from a model card",
  },
  {
    num: "03",
    label: "which makes every layer a decision",
    note: "each of those layers is behind a seam you own — moved on your schedule, not a vendor's release calendar",
  },
];

/**
 * The three claims, glanceable in one row rather than read as a sequence.
 *
 * The presentation changed with the wording: the number is now a quiet rail
 * marker rather than a heading, the label is the line you read, and the note is
 * visibly subordinate. Before, all three sat at nearly the same weight, so the
 * row read as three equal paragraphs and the eye had nowhere to land.
 */
export function ArgumentClaims() {
  return (
    <div className="grid w-full max-w-[var(--frame-w)] gap-px border border-hair bg-hair min-[860px]:grid-cols-3">
      {CLAIMS.map((c) => (
        <div key={c.num} className="flex flex-col gap-[0.5rem] bg-surface p-[1.3rem]">
          <span
            aria-hidden="true"
            className="font-mono text-[0.66rem] tracking-[var(--tracking-meta)] text-ink-mute"
          >
            {c.num}
          </span>
          <span className="font-mono text-[0.95rem] leading-[1.4] text-ink">{c.label}</span>
          <span className="text-[0.84rem] leading-[1.65] text-ink-soft">{c.note}</span>
        </div>
      ))}
    </div>
  );
}

/**
 * Retired on the owner's instruction this round: "there's the read the docs
 * button there right below — there's read the docs buttons all over the place,
 * I just get rid of it."
 *
 * Kept as a named export only so the import in `LandingPage` fails loudly if it
 * is ever wired back in without a decision. It renders nothing.
 */
export function ArgumentCta() {
  return null;
}
