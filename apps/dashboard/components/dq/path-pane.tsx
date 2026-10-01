import type { ReactNode } from "react";

/**
 * PathPane — modular pane frame. Header carries the slash-path (mirrors the
 * API route); body scrolls inside the frame so the page never does.
 */
export function PathPane({
  path,
  as_of,
  children,
}: {
  path: string;
  as_of?: string | null;
  children: ReactNode;
}) {
  return (
    <section className="flex min-h-0 flex-col border border-white/10" aria-label={path}>
      <header className="flex items-baseline justify-between gap-2 border-b border-white/10 px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider opacity-80">
        <span>{path}</span>
        {as_of ? <span>as of {as_of}</span> : null}
      </header>
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </section>
  );
}
