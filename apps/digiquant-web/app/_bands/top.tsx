"use client";

import { useEffect, type CSSProperties } from "react";
import { CtaLink } from "@digithings/ui";
import { QuantField } from "../_chrome/QuantField";
import { QuantWordmark } from "../_chrome/QuantWordmark";

const REPO = "https://github.com/digithings-ai/digithings";
const HERO_ACTION =
  "hero-action inline-flex h-auto items-center border border-hair bg-transparent px-[1rem] py-[0.85rem] font-mono text-[0.85rem] leading-[1.5] text-ink no-underline hover:bg-surface-2";

function rise(step: number): CSSProperties {
  return { "--rise": step } as CSSProperties;
}

/** Hero: full-viewport chart under the fixed nav (nav is transparent until scroll).
 *  Logo + copy + buttons settle first; then Vela builds in behind. */
export function TopBand() {
  useEffect(() => {
    // Raw load must start at the top — no restored mid-page scroll, no hash jump.
    if (window.location.hash) return;
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    window.scrollTo(0, 0);
  }, []);

  return (
    <section
      id="top"
      aria-labelledby="top-h"
      className="dq-hero relative isolate z-10 -mt-[var(--nav-shell-h,62px)] h-[100svh] min-h-[100svh] overflow-hidden border-b border-hair"
    >
      <QuantField />
      <div className="pointer-events-none relative mx-auto flex h-full min-h-0 w-full max-w-[64rem] flex-col items-center justify-center px-[var(--page-pad)] pb-[2.5rem] pt-[calc(var(--nav-shell-h,62px)+1.25rem)] text-center before:pointer-events-none before:absolute before:inset-0 before:-z-10 before:bg-[radial-gradient(ellipse_at_center,rgb(0_0_0/0.82),rgb(0_0_0/0.28)_46%,transparent_74%)] sm:px-[2.5rem]">
        <QuantWordmark className="block h-auto w-[264px] fill-current text-ink min-[380px]:w-[352px] sm:w-[528px] md:w-[616px]" />
        <h1
          id="top-h"
          className="hero-rise m-0 mt-[1.5rem] font-display text-[1.5rem] font-semibold leading-[1.25] tracking-[-0.02em] text-balance text-ink sm:text-[1.7rem]"
          style={rise(0)}
        >
          Quant research that shows its work.
        </h1>
        <p className="hero-rise m-0 mt-[0.75rem] max-w-[42rem] text-[0.9375rem] leading-[1.6] text-pretty text-ink-soft" style={rise(1)}>
          digiquant runs the daily research, sizes the risk, tests every idea against history and logs each decision. You run it in
          the terminal. This site shows it working.
        </p>
        <div className="hero-rise pointer-events-auto mt-[1.5rem] flex max-w-full flex-wrap items-center justify-center gap-[0.65rem]" style={rise(2)}>
          <CtaLink href="/app" variant="ghost" className={HERO_ACTION}>
            Open the terminal
          </CtaLink>
          <CtaLink href={REPO} external variant="ghost" className={HERO_ACTION}>
            GitHub
          </CtaLink>
        </div>
      </div>
    </section>
  );
}
