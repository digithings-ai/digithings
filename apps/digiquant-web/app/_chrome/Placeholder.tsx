import type { ReactNode } from "react";
import { Badge } from "@digithings/ui/ui";

/** Layout placeholder: dashed frame, a `placeholder` chip, a faint wireframe of the
 *  future content, and a visible design note saying what will go there. Nothing in
 *  it is wired to data, brokers or iframes. Every placeholder on the page uses this
 *  one shell so the grid reads the same everywhere. */
export function Placeholder({
  title,
  note,
  bodyClassName = "min-h-[14rem]",
  className = "",
  children,
}: {
  title: string;
  /** What this block will eventually show. Rendered as the design note. */
  note: string;
  bodyClassName?: string;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <figure role="group" aria-label={`${title} (placeholder)`} className={`m-0 flex min-w-0 flex-col border border-dashed border-hair ${className}`}>
      <div className="flex items-center justify-between gap-3 border-b border-dashed border-hair px-3 py-2 font-mono text-[0.68rem] text-ink-mute">
        <span className="truncate">{title}</span>
        <Badge variant="outline" className="shrink-0 border-dashed text-[0.62rem] text-ink-mute">
          placeholder
        </Badge>
      </div>
      <div aria-hidden="true" className={`flex-1 p-3 ${bodyClassName}`}>
        {children}
      </div>
      <figcaption className="border-t border-dashed border-hair px-3 py-2 text-[0.75rem] leading-[1.55] text-ink-soft">
        <span className="font-mono text-[0.65rem] uppercase tracking-[0.08em] text-ink-mute">design note </span>
        {note}
      </figcaption>
    </figure>
  );
}

/** Wireframe primitive: a hairline box used inside placeholder bodies. */
export function Wire({ className = "" }: { className?: string }) {
  return <span className={`block border border-hair ${className}`} />;
}
