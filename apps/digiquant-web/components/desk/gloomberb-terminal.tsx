import { CtaLink, GLOOMBERB_ATTRIBUTION, GLOOMBERB_TERMINAL_URL } from "@digithings/ui";

/** The Terminal slot. The Gloomberb terminal opens in a new tab. */
export function GloomberbTerminal() {
  return (
    <section aria-label="Terminal" className="m-px flex min-h-0 flex-1 flex-col bg-surface">
      <h1 className="m-0 flex h-7 shrink-0 items-center border-b border-hair px-2.5 font-mono text-[0.6875rem] font-normal tracking-[0.04em] text-ink-mute">
        Terminal
      </h1>
      <div className="flex flex-col items-start gap-2 px-2.5 py-2">
        <p className="m-0 font-mono text-[0.75rem] leading-[1.45] text-ink-mute">{GLOOMBERB_ATTRIBUTION}</p>
        <CtaLink href={GLOOMBERB_TERMINAL_URL} external variant="outline" size="sm">
          Open Terminal
        </CtaLink>
      </div>
    </section>
  );
}
