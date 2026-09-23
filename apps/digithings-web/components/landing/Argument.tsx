"use client";

/**
 * The argument — a seam diagram (v15 Stage 5, #4429; reworked Round 3).
 *
 * Owner direction, point 10: "'Why digithings' more creatively built out — a
 * visual explanation, not a long sequential readout."
 *
 * Owner direction, Round 3: "I wouldn't specifically name any of the modules…
 * I'd just explain how it's implemented in digithings, how it's integrated…
 * it's too direct. This section, it should be more explicative. So I'd give like
 * a good line or two per cell to explain exactly what we mean… And then I think
 * we could remove points one, two, and three below the table. I'd focus on
 * making the managed platform versus digithings the highlight here."
 *
 * Two changes this round:
 *
 *  - No module is named anywhere in the diagram. The right column describes the
 *    layer, not the package that fills it: the product names were doing the
 *    explaining, and to a reader who has not met the packages yet they explain
 *    nothing. The layer label already names the seam; the cell now says what
 *    living on that seam means for you.
 *  - Every cell is a line or two of explanation rather than a four-word
 *    fragment. The fragments ("their hosted runtime", "their account and rate
 *    limits") were the "too direct" reading the note objected to — they named
 *    the difference without saying what follows from it.
 *
 * The three claims that used to sit below the diagram are retired (see
 * `ArgumentClaims`), so the comparison is now the whole of the section.
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
 *  - Encryption is described by what it is — a JWT, signed and scoped, carried
 *    on the call — never by an unqualified superlative.
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
// whole claim. Each cell is a line or two: enough to say what the consequence
// is, not so much that the diagram turns back into the prose it replaced. No
// module is named — the layer label names the seam, and the sentence explains
// it.
const LAYERS: Layer[] = [
  {
    layer: "models",
    theirs:
      "one vendor's weights, on their release schedule and their price tiers — you run the models they ship, when they ship them",
    yours:
      "any provider behind one interface — the weights change without a line changing anywhere above them",
  },
  {
    layer: "retrieval",
    theirs:
      "their index, billed by the vector, tuned to their embedding family — your documents sit in their store",
    yours:
      "retrieval you point at a store you choose — the index, the embeddings and the documents stay yours",
  },
  {
    layer: "tools",
    theirs:
      "their tool registry, callable only from inside their runtime — the surface your agents reach is theirs to change",
    yours:
      "tool servers you run, reached over MCP — the same tools are callable from every agent in the stack",
  },
  {
    layer: "graph",
    theirs:
      "their runtime executes the graph — your orchestration runs on their machine, inside their limits",
    yours:
      "the same graph runs on your hosts — orchestration, retries and state never leave your network",
  },
  {
    layer: "keys",
    theirs:
      "one account, one key, their scopes and their rate limits — access is issued and revoked by them",
    yours:
      "keys you issue and revoke, JWT-signed and scoped on every call and every tool call, so permissions are yours to set",
  },
  {
    layer: "audit",
    theirs:
      "their logs, their retention window — the record of what ran is theirs to keep or to drop",
    yours:
      "an append-only log on your disk — every call, tool and result recorded where you can read it",
  },
  {
    layer: "hosts",
    theirs:
      "their cloud, in their regions, under their controls — the infrastructure is rented, never owned",
    yours: "your machine, VM or cluster — the same stack on metal you already run",
  },
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

/**
 * Retired on the owner's instruction this round: "I think we could remove points
 * one, two, and three below the table. I'd focus on making the managed platform
 * versus digithings the highlight here."
 *
 * The three claims restated, in prose, what the diagram above already shows —
 * the managed platform owns each layer, you own each seam — and they pushed the
 * section's weight back from the picture to a readout. The comparison is the
 * section now.
 *
 * Kept as a named export only so the import in `LandingPage` fails loudly if it
 * is ever wired back in without a decision. It renders nothing.
 */
export function ArgumentClaims() {
  return null;
}

/**
 * Retired on the owner's instruction in an earlier round: "there's the read the
 * docs button there right below — there's read the docs buttons all over the
 * place, I just get rid of it."
 *
 * Kept as a named export only so the import in `LandingPage` fails loudly if it
 * is ever wired back in without a decision. It renders nothing.
 */
export function ArgumentCta() {
  return null;
}
