import type { CSSProperties } from "react";
import { CtaLink, subsystems } from "@digithings/ui";
import { QuantField } from "../_chrome/QuantField";
import { QuantWordmark } from "../_chrome/QuantWordmark";
import { PIPELINE_STAGES } from "../_stages";

const REPO = "https://github.com/digithings-ai/digithings";
const HERO_ACTION =
  "hero-action inline-flex h-auto items-center border border-hair bg-transparent px-[1rem] py-[0.85rem] font-mono text-[0.85rem] leading-[1.5] text-ink no-underline hover:bg-surface-2";

const HERO_FACTS = [`${subsystems.length} subsystems`, `${PIPELINE_STAGES.length} pipeline stages`, "no live trading"] as const;

function rise(step: number): CSSProperties {
  return { "--rise": step } as CSSProperties;
}

/** Hero: the wordmark builds as bars over a plain bar chart. One line on what
 *  digiquant does, one on where the product lives, three actions and three facts. */
export function TopBand() {
  return (
    <section id="top" aria-labelledby="top-h" className="relative isolate z-10 overflow-hidden border-b border-hair">
      <QuantField />
      <div className="mx-auto flex min-h-[27rem] max-w-[64rem] flex-col items-center px-[var(--page-pad)] pb-[11rem] pt-[2.5rem] text-center sm:px-[2.5rem]">
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
          <CtaLink href="#workflow" variant="ghost" className={HERO_ACTION}>
            How a strategy gets built
          </CtaLink>
          <CtaLink href={REPO} external variant="ghost" className={HERO_ACTION}>
            GitHub
          </CtaLink>
        </div>
        <ul
          className="hero-rise m-0 mt-[1.4rem] flex list-none flex-wrap items-center justify-center gap-x-[0.6rem] gap-y-[0.3rem] p-0 font-mono text-[0.72rem] leading-[1.5] tracking-[0.02em] text-ink-mute"
          style={rise(3)}
          aria-label="Facts"
        >
          {HERO_FACTS.map((fact, index) => (
            <li key={fact} className="flex items-center gap-[0.6rem]">
              {index > 0 ? (
                <span aria-hidden="true" className="text-hair">
                  /
                </span>
              ) : null}
              {fact}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
