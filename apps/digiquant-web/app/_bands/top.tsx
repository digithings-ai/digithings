import { CopyCommand, CtaLink } from "@digithings/ui";
import { QuantField } from "../_chrome/QuantField";
import { QuantWordmark } from "../_chrome/QuantWordmark";

const REPO = "https://github.com/digithings-ai/digithings";
const HERO_ACTION =
  "inline-flex h-auto items-center border border-hair bg-transparent px-[1rem] py-[0.85rem] font-mono text-[0.85rem] leading-[1.5] text-ink no-underline hover:bg-surface-2";

/** Hero: the wordmark builds as bars over a streaming price panel. The counters
 *  and live strip land in the vertical slice. */
export function TopBand() {
  return (
    <section id="top" aria-labelledby="top-h" className="relative isolate z-10 overflow-hidden border-b border-hair">
      <QuantField />
      <div className="mx-auto flex min-h-[30rem] max-w-[64rem] flex-col items-center justify-center px-[var(--page-pad)] pb-[11rem] pt-[2.5rem] text-center">
        <QuantWordmark className="block h-auto w-[264px] fill-current text-inkmin-[380px]:w-[352px] sm:w-[528px] md:w-[616px]" />
        <h1 id="top-h" className="m-0 mt-[2rem] font-mono text-[1.5rem] font-semibold leading-[1.25] tracking-[-0.02em] text-ink sm:text-[1.7rem]">
          A quant research desk, in a glass box you own.
        </h1>
        <p className="m-0 mt-[0.75rem] max-w-[42rem] font-mono text-[0.875rem] leading-[1.6] text-ink-soft">
          Research runs daily, portfolio sizes the risk, and every run leaves a decision log.
        </p>
        <div className="mt-[1.75rem] flex max-w-full flex-wrap items-center justify-center gap-[0.65rem]">
          <CopyCommand
            className="w-fit max-w-full"
            samples={[{ label: "clone", protocol: "git clone", code: `git clone ${REPO}.git` }]}
            ariaLabel="Clone command"
            inline
          />
          <CtaLink href={REPO} external variant="ghost" className={HERO_ACTION}>
            GitHub
          </CtaLink>
          <CtaLink href="#pipeline" variant="ghost" className={HERO_ACTION}>
            Pipeline
          </CtaLink>
        </div>
      </div>
    </section>
  );
}
