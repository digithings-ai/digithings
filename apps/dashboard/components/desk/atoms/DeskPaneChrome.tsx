import type { ReactNode } from 'react';

export interface DeskPaneChromeProps {
  eyebrow?: string;
  title: string;
  chromePath: string;
  children: ReactNode;
}

/** Hairline pane frame. The body scrolls; the page does not. */
export function DeskPaneChrome({ eyebrow, title, chromePath, children }: DeskPaneChromeProps) {
  return (
    <section className="border border-hair bg-bg" data-testid="desk-pane" data-chrome-path={chromePath}>
      <header className="border-b border-hair bg-surface px-3 py-2">
        {eyebrow ? (
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-mute">{eyebrow}</p>
        ) : null}
        <h2 className="font-mono text-xs text-ink">{title}</h2>
        <p className="font-mono text-[10px] text-ink-mute">{chromePath}</p>
      </header>
      <div className="min-h-0 overflow-auto" data-desk-pane-scroll>
        {children}
      </div>
    </section>
  );
}
