import { BLOCKS, PAGES, layoutFor } from "../../../../clients/digiquant-tui/src/catalog";
import type { ReadResult } from "../../../../clients/digiquant-tui/src/read";
import { DeskFrame } from "./desk-frame";
import { PANE_GRID } from "./pages/pane";

const tone: Record<ReadResult["status"] | "loading", string> = {
  ok: "text-ink",
  empty: "text-ink-mute",
  loading: "text-ink-mute",
  stub: "text-ink-soft",
  error: "text-ink-soft",
};

function pageFor(path: string) {
  return PAGES.find((item) => item.path === path) ?? PAGES[0];
}

/** Catalog blocks for one page. The web desk and the terminal frame both paint this grid. */
export function DeskReadout({ path, reads }: { path: string; reads: Record<string, ReadResult | undefined> }) {
  const page = pageFor(path);
  const layout = layoutFor(page.path);
  return (
    <div className={PANE_GRID}>
      {layout.map((placement) => {
        const def = BLOCKS[placement.id];
        const read = reads[placement.id];
        const status = read?.status ?? "loading";
        const lines = read?.lines ?? ["loading…"];
        return (
          <section
            key={placement.id}
            aria-label={def.title}
            style={{ gridColumn: `${placement.x} / span ${placement.w}`, gridRow: `${placement.y} / span ${placement.h}` }}
            className="flex min-h-0 min-w-0 flex-col overflow-hidden bg-surface"
          >
            <h2 className="m-0 flex h-7 shrink-0 items-center border-b border-hair px-2.5 font-mono text-[0.6875rem] font-normal tracking-[0.04em] text-ink-mute">{def.title}</h2>
            <p className={`m-0 min-h-0 flex-1 overflow-auto whitespace-pre-wrap px-2.5 py-1.5 font-mono text-[0.75rem] leading-[1.45] tabular-nums ${tone[status]}`}>
              {lines.slice(0, 14).join("\n")}
            </p>
            <p className="m-0 flex h-7 shrink-0 items-center truncate border-t border-hair px-2.5 font-mono text-[0.6875rem] tracking-[0.04em] text-ink-mute tabular-nums">
              {read?.asOf ? `as of ${read.asOf}` : def.route}
            </p>
          </section>
        );
      })}
    </div>
  );
}

/** The catalog pages inside the web desk frame. */
export function DeskView({ path, reads }: { path: string; reads: Record<string, ReadResult | undefined> }) {
  const page = pageFor(path);
  return (
    <DeskFrame current={page.path}>
      <DeskReadout path={path} reads={reads} />
    </DeskFrame>
  );
}
