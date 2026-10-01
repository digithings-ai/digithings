import type { ReactNode } from 'react';

/** Window atom — title bar (`NN / label`, optional right slot) + scrolling body. */
export function Window({ no, label, right, children }: { no: string; label: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="win" aria-label={label}>
      <header className="win-bar">
        <span className="ey">{no} / {label}</span>
        {right ? <span>{right}</span> : null}
      </header>
      <div className="win-body">{children}</div>
    </section>
  );
}
