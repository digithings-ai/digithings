import { GLOOMBERB_TERMINAL_URL } from "../../../../packages/ui/src/lib/gloomberb";

/** The Terminal slot. The frame is the Gloomberb terminal. */
export function GloomberbTerminal() {
  return (
    <section aria-label="Terminal" className="m-1 flex min-h-0 flex-1 flex-col border border-hair bg-surface">
      <h1 className="m-0 shrink-0 border-b border-hair px-2 py-1 text-[0.65rem] font-normal text-ink-mute">
        Terminal
      </h1>
      <iframe
        title="Terminal"
        src={GLOOMBERB_TERMINAL_URL}
        className="block min-h-0 w-full flex-1 border-0 bg-black"
      />
    </section>
  );
}
