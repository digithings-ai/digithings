"use client";

import { useEffect, useRef } from "react";
import { FaqList } from "./Sections";
import { LiveAsk } from "./LiveAsk";

/**
 * The FAQ band's scroll-driven zoom-morph (#4429, branch claude/home-variants).
 *
 * The owner's ask: "show the chat container large and then it retracts and it
 * shows some of the frequently asked questions or you could ask in the live
 * chat". The mechanic is the reference gallery's **zoom-morph** section
 * transition (`apps/reference/components/effects/section-morph.tsx`): a pinned
 * stage whose scroll progress is read by a passive scroll handler that writes
 * transforms straight to refs (no `useScroll`, no per-frame React state) and
 * collapses to a static, un-pinned block under `prefers-reduced-motion`.
 *
 * ## Why this is app-local, not a kit primitive
 *
 * It is the same *mechanic* as the specimen, but not the same *part*. The
 * specimen morphs one hero panel into a docked card beside synthetic copy; here
 * the thing that moves is a real, interactive product surface (the live
 * digichat embed) that must stay mounted, stay focusable and keep its conversation
 * across the whole motion, and the geometry is the band's own two-column grid.
 * A generic `MorphSection` would have to take its docked geometry, its copy
 * layout and its interactive child as configuration — generalising a one-off,
 * which MIGRATION.md warns against. It is also, like the `/variants/mixed`
 * stack showcase on this same branch, still an exploration the owner has not
 * picked yet; if it survives the picking it promotes into the kit and the
 * app-local block in globals.css is deleted with it. The scroll→refs write,
 * the pinned track and the reduced-motion fallback all mirror the promoted
 * `<StackingPanels>` primitive so the pattern stays recognisable.
 *
 * ## Mechanics and geometry
 *
 * The track (`.faq-morph`) is the band's natural height plus ~0.9 viewport of
 * morph scroll; the stage (`.faq-morph__pin`) is `position: sticky` under the
 * nav. Progress `p` is 0 the instant the stage pins and 1 when the track
 * releases, so every scroll pixel drives the morph (no dead hold, and the
 * release lands exactly on the docked layout, so there is no jump).
 *
 * At `p = 0` the chat column's inner wrapper is scaled up toward the frame
 * width (height-capped on short viewports) and translated so its centre sits
 * over the frame's centre, vertically centred in the nav-free viewport — it
 * reads as the band. At `p = 1` the transform is identity: the chat is back in
 * the right column and the FAQ list has risen in on the left. `dx`, `dy`, the
 * scale `S` and the morph distance are *measured* on mount and on resize (not
 * hard-coded), so the start state is exact at every width. The scale is capped
 * so the enlarged chat fits between the nav and the viewport floor. That cap is
 * load-bearing in two ways: it keeps the enlarged box from extending above its
 * own layout box (so it can never bleed up into the Voices band while the band
 * is scrolling into view), and — with the box centred on the frame — it keeps
 * the whole morph inside the frame horizontally, so the band adds no horizontal
 * overflow at any width.
 *
 * The chat wrapper is a *descendant* of the sticky stage and the stage itself is
 * never transformed — only the inner wrapper moves — so `position: sticky`
 * keeps working. The FAQ column fades and rises on a slightly later window
 * (`FAQ_DELAY`) so the retract reads first and the questions arrive second, but
 * it still finishes exactly at `p = 1` rather than holding.
 *
 * ## Fallbacks
 *
 * Below the grid's 960px two-column breakpoint and under `prefers-reduced-motion`
 * the effect never runs (`MORPH_MEDIA`), no inline height or transform is ever
 * written, and the band is today's static two-column layout (single column on
 * narrow screens). With no JS at all the same natural layout renders, because
 * the inline track height only ever comes from the effect. The `details`/
 * `summary` semantics, the h2, the `#faq` id and the `full screen chat` handoff
 * are untouched: the morph moves pixels, not markup.
 */

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

/** Active only where the grid is two columns and motion is welcome. */
const MORPH_MEDIA = "(min-width: 960px) and (prefers-reduced-motion: no-preference)";

/** Extra scroll the morph gets, in viewport heights (a short, continuous move). */
const MORPH_VH = 0.9;

/** Clearance kept under the nav when the chat is scaled up, so it never clips. */
const NAV_CLEARANCE_PX = 24;

/** The FAQ window: revealed after the retract has started, finished at p = 1. */
const FAQ_DELAY = 0.15;
const FAQ_SPAN = 0.85;

export function FaqMorph({ embedOrigin }: { embedOrigin: string }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const pinRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const chatInnerRef = useRef<HTMLDivElement>(null);
  const faqRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const pin = pinRef.current;
    const grid = gridRef.current;
    const chat = chatRef.current;
    const chatInner = chatInnerRef.current;
    const faq = faqRef.current;
    if (!wrap || !pin || !grid || !chat || !chatInner || !faq) return;

    const mq = window.matchMedia(MORPH_MEDIA);

    // Measured geometry, recomputed on resize and on content resize.
    let dx = 0;
    let dy = 0;
    let scale = 1;
    let distance = 0;
    let stickyTop = 78;

    const measure = () => {
      stickyTop = parseFloat(getComputedStyle(pin).top) || 78;

      const gridRect = grid.getBoundingClientRect();
      const frameW = gridRect.width || 1;
      const frameCenterX = gridRect.left + frameW / 2;

      // The column's box is untransformed (only its child moves), and
      // `offsetHeight` is layout height regardless of any transform — so these
      // stay correct even if `measure` runs while a transform is applied.
      const chatRect = chat.getBoundingClientRect();
      const chatW = chat.offsetWidth || 1;
      const chatH = chatInner.offsetHeight || 1;
      const chatCenterX = chatRect.left + chatRect.width / 2;

      // Start centred on the frame, docked on the right column.
      dx = frameCenterX - chatCenterX;
      dy = (window.innerHeight - stickyTop - chatH) / 2;
      // Fill the frame width, but never taller than the nav-free viewport.
      const fitH = (window.innerHeight - stickyTop - NAV_CLEARANCE_PX) / chatH;
      scale = Math.max(1, Math.min(frameW / chatW, fitH));

      distance = Math.round(window.innerHeight * MORPH_VH);
      wrap.style.height = `${Math.round(pin.getBoundingClientRect().height + distance)}px`;
    };

    const apply = (p: number) => {
      // Ease-out: the chat retracts promptly, then settles.
      const me = 1 - Math.pow(1 - p, 3);
      const u = 1 - me;
      chatInner.style.transform =
        `translate(${dx * u}px, ${dy * u}px) scale(${1 + (scale - 1) * u})`;

      const c = clamp((p - FAQ_DELAY) / FAQ_SPAN, 0, 1);
      const ce = c * c * (3 - 2 * c); // smoothstep
      faq.style.opacity = `${ce}`;
      faq.style.transform = `translateY(${(1 - ce) * 24}px)`;
      // While the large chat covers it, the faded FAQ must not take the click.
      faq.style.pointerEvents = p > 0.6 ? "auto" : "none";
    };

    const reset = () => {
      wrap.style.height = "";
      chatInner.style.transform = "";
      faq.style.opacity = "";
      faq.style.transform = "";
      faq.style.pointerEvents = "";
    };

    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const top = wrap.getBoundingClientRect().top;
        apply(distance > 0 ? clamp((stickyTop - top) / distance, 0, 1) : 0);
        ticking = false;
      });
    };

    const onResize = () => {
      measure();
      onScroll();
    };

    let observer: ResizeObserver | undefined;

    const enable = () => {
      measure();
      onScroll();
      observer = new ResizeObserver(onResize);
      observer.observe(pin);
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onResize, { passive: true });
    };

    const disable = () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
      observer?.disconnect();
      reset();
    };

    const onMediaChange = () => {
      if (mq.matches) enable();
      else disable();
    };

    onMediaChange();
    mq.addEventListener("change", onMediaChange);
    return () => {
      mq.removeEventListener("change", onMediaChange);
      disable();
    };
  }, []);

  return (
    <div className="faq-morph" ref={wrapRef}>
      <div className="faq-morph__pin" ref={pinRef}>
        {/* The docked two-column grid is the end state, and the reduced-motion /
            no-JS layout. The chat column takes the larger share, so the
            conversation has room to be read without the frame changing height
            (round 5 — "just to give more room for the chat"). */}
        <div
          ref={gridRef}
          className="mx-auto grid max-w-[var(--frame-w)] gap-[2.4rem] min-[960px]:grid-cols-[minmax(0,0.78fr)_minmax(0,1.22fr)]"
        >
          <div ref={faqRef} className="faq-morph__faq flex flex-col gap-[1.6rem]">
            <h2 className="m-0 font-mono text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink">
              Questions, answered
            </h2>
            <FaqList />
          </div>
          <div ref={chatRef} className="faq-morph__chat min-w-0">
            <div ref={chatInnerRef} className="faq-morph__chat-inner">
              <LiveAsk embedOrigin={embedOrigin} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
