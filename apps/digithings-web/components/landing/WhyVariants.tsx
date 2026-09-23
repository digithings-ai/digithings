"use client";

/**
 * The four `#why` variations (`/variants/why`, #4429 round 8).
 *
 * The owner's ask, verbatim: "First of all, the arrow should appear on the line
 * itself, kind of breaking the line apart. Maybe we could design a few versions
 * of this and you could host it on a local host app … we kind of show the
 * managed platform first and then we show all the digithings improvements of how
 * it kind of changes the managed platform and turns it into a fully modular,
 * customizable infrastructure that you actually own and can scale much easier at
 * lower costs and higher efficiency and create custom apps for it."
 *
 * Four compositions of the same argument, stacked so one can be picked and folded
 * into `Argument.tsx`. They share the seven layers the live band already argues
 * (`LAYERS` from `Argument.tsx`) and the same seven in the diagrams
 * (`WHY_PARTS` from `why-diagrams.tsx`), so the copy cannot drift between them.
 *
 * HONESTY (binding, inherited from `Argument.tsx`): no vendor is named — the left
 * side is the SHAPE, not an accusation; nothing is asserted about any platform's
 * unpublished pricing or contract terms; there are no dollar amounts, no
 * percentages and no "Nx cheaper" (the repo has no sourced comparison numbers);
 * no performance or trading figures; and the key claim stays "a JWT, signed and
 * scoped, carried on the call".
 *
 * MECHANICS: one passive `scroll` listener per version writes a single
 * `--why-p` custom property (0 → 1) straight to the DOM — no per-frame React
 * state, the pattern proven by `ArgumentSeams`, `FaqMorph` and the reference's
 * `section-morph`. Under `prefers-reduced-motion` no listener is attached and no
 * height is written, so the CSS falls back to the finished state
 * (`var(--why-p, 1)`).
 */
import { useEffect, useRef, type RefObject } from "react";
import { LAYERS } from "./Argument";
import { EvolutionGraph, LayerExplode, MonolithToGraph } from "./why-diagrams";

const NO_MOTION = "(prefers-reduced-motion: no-preference)";

const headline = "m-0 font-mono text-[clamp(1.3rem,2.4vw,1.85rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink";
const lede = "m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft";

/**
 * Drive one version's scroll progress.
 *
 * Writes `--why-p` on the wrapper (0 → 1 across a `distanceVh`-tall window after
 * the pin sticks) and sets the wrapper's height so the pin has something to
 * travel through. `onMeasure` runs after each measure so a version can publish
 * geometry the CSS needs (V1 measures the drawer's travel).
 */
function useWhyProgress(
  wrapRef: RefObject<HTMLDivElement | null>,
  pinRef: RefObject<HTMLDivElement | null>,
  distanceVh: number,
  onMeasure?: (wrap: HTMLDivElement, pin: HTMLDivElement) => void,
) {
  const measureRef = useRef(onMeasure);
  /* Kept in a ref so a caller passing an inline `onMeasure` cannot re-run the
     scroll effect; assigned in an effect, not during render. */
  useEffect(() => {
    measureRef.current = onMeasure;
  });

  useEffect(() => {
    const wrap = wrapRef.current;
    const pin = pinRef.current;
    if (!wrap || !pin) return;
    const motion = typeof matchMedia === "function" ? matchMedia(NO_MOTION) : null;
    let distance = 0;
    let raf = 0;

    const measure = () => {
      distance = Math.round(window.innerHeight * distanceVh);
      wrap.style.height = `${pin.offsetHeight + distance}px`;
      measureRef.current?.(wrap, pin);
    };
    const apply = (p: number) => wrap.style.setProperty("--why-p", p.toFixed(4));
    const reset = () => {
      wrap.style.height = "";
      wrap.style.removeProperty("--why-p");
    };
    const onScroll = () => {
      if (raf !== 0) return;
      raf = window.requestAnimationFrame(() => {
        raf = 0;
        const stickyTop = Number.parseFloat(getComputedStyle(pin).top) || 0;
        const raw = distance > 0 ? (stickyTop - wrap.getBoundingClientRect().top) / distance : 1;
        apply(Math.max(0, Math.min(1, raw)));
      });
    };
    const onResize = () => {
      measure();
      onScroll();
    };
    const enable = () => {
      measure();
      onScroll();
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onResize);
    };
    const disable = () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
      reset();
    };

    if (!motion || motion.matches) enable();
    const onChange = () => (motion?.matches ? enable() : disable());
    motion?.addEventListener("change", onChange);
    return () => {
      motion?.removeEventListener("change", onChange);
      disable();
      if (raf !== 0) window.cancelAnimationFrame(raf);
    };
  }, [wrapRef, pinRef, distanceVh]);
}

/** The shared frame: a measured track, a sticky pin, and a version label. */
function Version({
  index,
  title,
  note,
  children,
  distanceVh,
  onMeasure,
}: {
  index: string;
  title: string;
  note: string;
  children: (refs: {
    wrapRef: RefObject<HTMLDivElement | null>;
    pinRef: RefObject<HTMLDivElement | null>;
  }) => React.ReactNode;
  distanceVh: number;
  onMeasure?: (wrap: HTMLDivElement, pin: HTMLDivElement) => void;
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const pinRef = useRef<HTMLDivElement | null>(null);
  useWhyProgress(wrapRef, pinRef, distanceVh, onMeasure);
  return (
    <section className="why-v">
      <div className="why-v__head">
        <span className="why-v__index">{index}</span>
        <h2 className={headline}>{title}</h2>
        <p className={lede}>{note}</p>
      </div>
      <div ref={wrapRef} className="why-v__wrap">
        <div ref={pinRef} className="why-v__pin">
          {children({ wrapRef, pinRef })}
        </div>
      </div>
    </section>
  );
}

/* ═══ V1 — the seam on the rule ════════════════════════════════════════════ */

/**
 * Today's seven-layer comparison, with the centre column replaced by ONE
 * continuous hairline per row that the arrow punches through.
 *
 * The rule is a single absolutely-positioned line spanning the whole row; the
 * arrow sits on top of it with the row's own surface behind it, so the line
 * reads as broken by the arrow rather than as two columns with a gap between
 * them. The drawer and the typewriter fill are unchanged from the live band.
 */
function V1SeamOnRule() {
  const gridRef = useRef<HTMLDivElement | null>(null);
  return (
    <Version
      index="01"
      title="The seam on the rule"
      note="The comparison we have now, with the arrow sitting on a single continuous rule — the line runs edge to edge and the arrow breaks it. The digithings column slides over the managed-platform column as the drawer opens, and its copy types itself in word by word."
      distanceVh={0.3}
      onMeasure={(wrap, pin) => {
        const grid = gridRef.current;
        if (!grid) return;
        const panel = grid.querySelector<HTMLElement>('[data-seam="panel"]');
        const seam = grid.querySelector<HTMLElement>('[data-seam="seam"]');
        if (!panel || !seam) return;
        grid.style.setProperty("--seam-travel", `${panel.offsetWidth + seam.offsetWidth}px`);
        void pin;
      }}
    >
      {() => (
        <div ref={gridRef} className="why-seam">
          <div className="why-seam__row why-seam__row--head">
            <p className="why-seam__col-label">the managed platform</p>
            <span data-seam="seam" className="why-seam__seam why-seam__head">
              <span className="why-seam__arrow">⇄</span>
            </span>
            <p data-seam="panel" className="why-seam__col-label why-seam__col-label--own">
              digithings
            </p>
          </div>
          {LAYERS.map((layer) => (
            <div key={layer.layer} className="why-seam__row">
              <span className="why-seam__rule" aria-hidden="true" />
              <div className="why-seam__theirs">
                <span className="why-seam__layername">{layer.layer}</span>
                <span className="why-seam__copy">{layer.theirs}</span>
              </div>
              <span data-seam="seam" className="why-seam__seam">
                <span className="why-seam__arrow">⇄</span>
              </span>
              <div data-seam="panel" className="why-seam__yours">
                <span className="why-seam__copy">
                  {layer.yours.split(" ").map((word, i, words) => (
                    <span
                      key={`${word}-${i}`}
                      className="why-seam__word"
                      style={{ "--i": i, "--n": words.length } as React.CSSProperties}
                    >
                      {i < words.length - 1 ? `${word} ` : word}
                    </span>
                  ))}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Version>
  );
}

/* ═══ V2 — the monolith comes apart into the graph ════════════════════════ */

function V2Morph() {
  return (
    <Version
      index="02"
      title="Rent the stack, or own it."
      note="One bounded whole on the left: seven layers inside a single boundary, one account, one release schedule. As you scroll, the boundary dissolves and the same seven things travel out to where they actually run — each one landing with the seam you get back."
      distanceVh={0.7}
    >
      {() => <MonolithToGraph />}
    </Version>
  );
}

/* ═══ V3 — the exploded layer stack ═══════════════════════════════════════ */

function V3Explode() {
  return (
    <Version
      index="03"
      title="One bill, or one infrastructure."
      note="The same seven slabs, flush behind a single boundary, pulling apart as you scroll. The least machinery of the four: nothing moves but the gap, and each layer names the seam it becomes."
      distanceVh={0.55}
    >
      {() => <LayerExplode />}
    </Version>
  );
}

/* ═══ V4 — the three-state evolution ══════════════════════════════════════ */

const EVO_STATES = [
  {
    key: 1 as const,
    title: "Rented",
    line: "One vendor's stack. One account, one bill, one release schedule — and you are outside the boundary.",
  },
  {
    key: 2 as const,
    title: "Modular",
    line: "The same seven layers, each one a seam you can move. No layer assumes the others are the same vendor's.",
  },
  {
    key: 3 as const,
    title: "Yours",
    line: "Your hosts, your keys, your providers — and every capability is a REST endpoint, an MCP tool, a CLI and a container to build your own app on.",
  },
];

/**
 * Three frames, one per scroll third, cross-fading the same diagram. Ends on a
 * benefit ledger written as structural consequences — what changes, not what it
 * will save you, because nothing here is a measured number.
 */
const LEDGER: { claim: string; because: string }[] = [
  {
    claim: "you pay providers, not a platform",
    because: "one bill becomes your own provider accounts — no per-seat or per-call rent on top",
  },
  {
    claim: "a layer swaps without a migration",
    because: "no module assumes you are running any other one",
  },
  {
    claim: "each layer scales where it already runs",
    because: "your metal, your region — there is no vendor capacity ceiling to queue behind",
  },
  {
    claim: "you ship your own apps on top",
    because: "every capability is a REST endpoint, an MCP tool, a CLI command and a container",
  },
];

function V4Evolution() {
  return (
    <Version
      index="04"
      title="A platform you buy from. An infrastructure you own."
      note="Three states on one scroll: rented, modular, yours. The diagram is the same seven layers the whole way through — only the arrangement changes."
      distanceVh={1.1}
    >
      {() => (
        <div className="why-evo">
          <div className="why-evo__stage">
            {EVO_STATES.map((state, i) => (
              <div key={state.key} className={`why-evo__frame why-evo__frame--${i + 1}`}>
                <EvolutionGraph frame={state.key} />
              </div>
            ))}
          </div>
          <div className="why-evo__legend">
            {EVO_STATES.map((state, i) => (
              <div key={state.key} className={`why-evo__legend-item why-evo__legend-item--${i + 1}`}>
                <span className="why-evo__step">{`0${i + 1}`}</span>
                <span className="why-evo__title">{state.title}</span>
                <span className="why-evo__line">{state.line}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Version>
  );
}

/** The ledger under V4 — structural consequences, never a figure. */
function BenefitLedger() {
  return (
    <ul className="why-ledger">
      {LEDGER.map((row) => (
        <li key={row.claim} className="why-ledger__row">
          <span className="why-ledger__claim">{row.claim}</span>
          <span className="why-ledger__because">{row.because}</span>
        </li>
      ))}
    </ul>
  );
}

export function WhyVariants() {
  return (
    <div className="why-variants">
      <V1SeamOnRule />
      <V2Morph />
      <V3Explode />
      <V4Evolution />
      <section className="why-v">
        <div className="why-v__head">
          <span className="why-v__index">ledger</span>
          <h2 className={headline}>What actually changes</h2>
          <p className={lede}>
            The four claims behind &ldquo;cheaper, more efficient, easier to scale, yours to build
            on&rdquo; — written as what structurally changes, because none of these is a number we
            can publish and none of them is a promise about anyone else&rsquo;s contract.
          </p>
        </div>
        <BenefitLedger />
      </section>
    </div>
  );
}
