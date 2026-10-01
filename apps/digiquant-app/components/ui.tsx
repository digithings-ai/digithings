import Link from 'next/link';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

/** Standard primitives. Blocks compose these; borders/spacing/fonts live in globals.css only. */

export type BadgeTone = 'plain' | 'ok' | 'wip' | 'gap' | 'unavailable' | 'live';
export function Badge({ tone = 'plain', children }: { tone?: BadgeTone; children: ReactNode }) {
  return <span className={`badge ${tone}`}>[{children}]</span>;
}

/** Inline "Label value" pairs. Values may be null → "—". */
export function MetaStrip({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <div className="meta">
      {items.map((m) => (
        <span key={m.label}>{m.label} <b>{m.value ?? '—'}</b></span>
      ))}
    </div>
  );
}

export function PageBand({ path, title, lede, meta }: { path: string; title: string; lede?: string; meta?: { label: string; value: ReactNode }[] }) {
  return (
    <header className="band">
      <div className="band-path">{path}</div>
      <h1 className="band-h">{title}</h1>
      {lede ? <p className="band-lede">{lede}</p> : null}
      {meta ? <MetaStrip items={meta} /> : null}
    </header>
  );
}

export function Tabs({ tabs, active }: { tabs: { href: string; label: string }[]; active: string }) {
  return (
    <nav className="tabs" aria-label="Sections">
      {tabs.map((t) => (
        <Link key={t.href} href={t.href} className="tab" aria-current={t.href === active ? 'page' : undefined}>{t.label}</Link>
      ))}
    </nav>
  );
}

export function KvList({ rows }: { rows: { k: string; v: ReactNode; mono?: boolean }[] }) {
  return (
    <dl className="kv">
      {rows.map((r) => (
        <div key={r.k} className="kv-row">
          <dt>{r.k}</dt>
          <dd className={r.mono ? 'mono' : undefined}>{r.v ?? '—'}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Prose({ lead, children }: { lead?: string; children?: ReactNode }) {
  return (
    <div className="prose">
      {lead ? <p className="lead">{lead}</p> : null}
      {children}
    </div>
  );
}

export function BulletList({ items }: { items: string[] }) {
  return <ul className="plain">{items.map((t, i) => <li key={i}>{t}</li>)}</ul>;
}

/** Empty / loading / error with a reason and next actions. One layout for all three. */
export function StateBlock({ kind, title, why, next }: { kind: 'empty' | 'loading' | 'error'; title: string; why?: string; next?: { label: string; href?: string; onClick?: () => void }[] }) {
  return (
    <div className={`state ${kind}`} role={kind === 'error' ? 'alert' : undefined} aria-busy={kind === 'loading' || undefined}>
      <p className="state-t">{title}</p>
      {why ? <p className="state-w">{why}</p> : null}
      {next?.length ? (
        <p className="state-n">
          {next.map((n) => (n.href ? <Link key={n.label} href={n.href}>{n.label} →</Link> : <button key={n.label} type="button" className="btn" onClick={n.onClick}>{n.label}</button>))}
        </p>
      ) : null}
    </div>
  );
}

export function SoonBar({ tag = 'soon', children }: { tag?: 'soon' | 'wip'; children: ReactNode }) {
  return <div className="soonbar" role="note"><Badge tone="wip">{tag}</Badge> <span>{children}</span></div>;
}

export function Button({ primary, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { primary?: boolean }) {
  return <button type="button" {...p} className={`btn${primary ? ' primary' : ''}`} />;
}
