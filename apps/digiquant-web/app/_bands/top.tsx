import type { CSSProperties } from "react";
import { CtaLink } from "@digithings/ui";
import { QuantField } from "../_chrome/QuantField";
import { QuantWordmark } from "../_chrome/QuantWordmark";

const REPO = "https://github.com/digithings-ai/digithings";
const HERO_ACTION =
  "hero-action inline-flex h-auto items-center border border-hair bg-transparent px-[1rem] py-[0.85rem] font-mono text-[0.85rem] leading-[1.5] text-ink no-underline hover:bg-surface-2";

function rise(step: number): CSSProperties {
  return { "--rise": step } as CSSProperties;
}

/** Hero: the wordmark over an illustrative candlestick chart that keeps moving,
 *  with a crosshair over the whole hero (and only the hero). One line on what
 *  digiquant does, one on where the product lives, two actions. */
export function TopBand() {
  return (
    <section id="top" aria-labelledby="top-h" className="dq-hero relative isolate z-10 overflow-hidden border-b border-hair">
      <QuantField />
      <div className="mx-auto flex min-h-[27rem] max-w-[64rem] flex-col items-center justify-center px-[var(--page-pad)] pb-[15rem] pt-[2.5rem] text-center sm:px-[2.5rem] lg:min-h-[calc(100svh-var(--nav-shell-h,62px))]">
        <QuantWordmark className="block h-auto w-[264px] fill-current text-ink min-[380px]:w-[352px] sm:w-[528px] md:w-[616px]" />
        <h1
          id="top-h"
          className="hero-rise m-0 mt-[2rem] font-display text-[1.5rem] font-semibold leading-[1.25] tracking-[-0.02em] text-balance text-ink sm:text-[1.7rem]"
          style={rise(0)}
        >
          Quant research that shows its work.
        </h1>
        <p className="hero-rise m-0 mt-[0.75rem] max-w-[42rem] text-[0.9375rem] leading-[1.6] text-pretty text-ink-soft" style={rise(1)}>
          digiquant runs daily research, sizes the risk and backtests on NautilusTrader, and logs every decision. You use it in
          the dashboard. This site shows it working.
        </p>
        <div className="hero-rise mt-[1.75rem] flex max-w-full flex-wrap items-center justify-center gap-[0.65rem]" style={rise(2)}>
          <CtaLink href="#dashboard" variant="ghost" className={HERO_ACTION}>
            See the dashboard
            <span aria-hidden="true" className="hero-action__arrow">
              ↓
            </span>
          </CtaLink>
          <CtaLink href={REPO} external variant="ghost" className={HERO_ACTION}>
            GitHub
          </CtaLink>
        </div>
      </div>
    </section>
  );
}
