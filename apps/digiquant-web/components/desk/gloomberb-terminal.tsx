import { CtaLink, GLOOMBERB_ATTRIBUTION, GLOOMBERB_TERMINAL_URL } from "@digithings/ui";

/** The Terminal slot. The Gloomberb terminal opens in a new tab. */
export function GloomberbTerminal() {
  return (
    <section aria-label="Terminal" className="m-1 flex min-h-0 flex-1 flex-col border border-hair bg-surface">
      <h1 className="m-0 shrink-0 border-b border-hair px-2 py-1 text-[0.65rem] font-normal text-ink-mute">
        Terminal
      </h1>
      <div className="flex flex-col items-start gap-2 px-2 py-2">
        <p className="m-0 text-[0.7rem] text-ink-mute">{GLOOMBERB_ATTRIBUTION}</p>
        <CtaLink href={GLOOMBERB_TERMINAL_URL} external variant="outline" size="sm">
          Open Terminal
        </CtaLink>
      </div>
    </section>
  );
}
