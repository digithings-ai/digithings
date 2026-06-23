'use client';

import { FileText } from 'lucide-react';

export default function DigestBrief({
  digest,
}: {
  digest: { run_date: string; summary: string; key_themes: string[]; doc_count: number; broker_count: number } | null;
}) {
  if (!digest) {
    return (
      <section className="glass-card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Digest brief</h2>
        <p className="mt-2 text-sm text-text-muted">No digest for today yet.</p>
      </section>
    );
  }
  return (
    <section className="glass-card flex flex-col gap-2 p-5">
      <header className="flex items-baseline gap-2">
        <FileText size={15} className="shrink-0 text-fin-blue" aria-hidden />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Digest brief</h2>
        <span className="ml-auto font-mono text-[10px] text-text-muted">
          {digest.doc_count} docs · {digest.broker_count} brokers
        </span>
      </header>
      <p className="whitespace-pre-line text-sm leading-relaxed text-text-primary">{digest.summary}</p>
      {digest.key_themes.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {digest.key_themes.map((t) => (
            <span key={t} className="rounded-full border border-border-subtle px-2.5 py-0.5 text-[11px] text-text-secondary">
              {t}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
