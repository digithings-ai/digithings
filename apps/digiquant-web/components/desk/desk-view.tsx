import { BLOCKS, PAGES, layoutFor } from "../../../../clients/digiquant-tui/src/catalog";
import type { ReadResult } from "../../../../clients/digiquant-tui/src/read";
import { deskHref } from "./paths";

const tone: Record<ReadResult["status"] | "loading", string> = {
  ok: "text-ink",
  empty: "text-ink-mute",
  loading: "text-ink-mute",
  stub: "text-ink-soft",
  error: "text-ink-soft",
};

/** The terminal pages. One block per official read, placed on the 12×12 grid. */
export function DeskView({ path, reads }: { path: string; reads: Record<string, ReadResult | undefined> }) {
  const page = PAGES.find((item) => item.path === path) ?? PAGES[0];
  const layout = layoutFor(page.path);
  return (
    <div className="flex h-full min-h-0 flex-col bg-black font-mono text-ink">
      <header className="flex h-8 shrink-0 items-center gap-3 border-b border-hair px-3 text-[0.7rem]">
        <a href="/" className="text-ink no-underline">
          digiquant
        </a>
        <span className="text-ink-mute">
          {page.label} {page.path}
        </span>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Pages" className="w-44 shrink-0 overflow-auto border-r border-hair py-2 text-[0.75rem]">
          {PAGES.map((item) => {
            const current = item.path === page.path;
            const child = item.path.split("/").filter(Boolean).length > 1;
            return (
              <a
                key={item.path}
                href={deskHref(item.path)}
                aria-current={current ? "page" : undefined}
                className={`block py-0.5 no-underline ${child ? "pl-6" : "pl-3"} ${current ? "text-ink" : "text-ink-mute"}`}
              >
                {item.label}
              </a>
            );
          })}
        </nav>
        <div className="grid min-h-0 flex-1 grid-cols-12 grid-rows-12 gap-1 p-1">
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
                className="flex min-h-0 min-w-0 flex-col overflow-hidden border border-hair bg-surface"
              >
                <h2 className="m-0 shrink-0 border-b border-hair px-2 py-1 text-[0.65rem] font-normal text-ink-mute">{def.title}</h2>
                <p className={`m-0 min-h-0 flex-1 overflow-auto whitespace-pre-wrap px-2 py-1 text-[0.7rem] leading-[1.45] ${tone[status]}`}>
                  {lines.slice(0, 14).join("\n")}
                </p>
                <p className="m-0 shrink-0 truncate border-t border-hair px-2 py-0.5 text-[0.6rem] text-ink-mute">
                  {read?.asOf ? `as of ${read.asOf}` : def.route}
                </p>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}
