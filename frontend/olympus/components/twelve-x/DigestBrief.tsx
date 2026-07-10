'use client';

import { FileText } from 'lucide-react';

import { SafeMarkdown } from '@/components/SafeMarkdown';

export default function DigestBrief({
  digest,
}: {
  digest: { run_date: string; summary: string; key_themes: string[]; doc_count: number; broker_count: number } | null;
}) {
  if (!digest) {
    return (
      <section className="glass-card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-soft">Digest brief</h2>
        <p className="mt-2 text-sm text-ink-mute">No digest for today yet.</p>
      </section>
    );
  }
  return (
    <section className="glass-card flex flex-col gap-2 p-5">
      <header className="flex items-baseline gap-2">
        <FileText size={15} className="shrink-0 text-accent" aria-hidden />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-soft">Digest brief</h2>
        <span className="ml-auto font-mono text-[10px] text-ink-mute">
          {digest.doc_count} docs · {digest.broker_count} brokers
        </span>
      </header>
      {/* The pipeline-written summary renders through SafeMarkdown (sanitizer
          stays — REM-076) inside the canonical .chat-md typography scope.
          `whitespace-pre-line` is kept ON PURPOSE: react-markdown emits soft
          breaks as literal "\n" text nodes, so plain-text summaries keep their
          exact pre-markdown line layout while real markdown (emphasis, lists,
          tables) now picks up the shared grammar. */}
      <SafeMarkdown className="whitespace-pre-line">{digest.summary}</SafeMarkdown>
      {digest.key_themes.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {digest.key_themes.map((t) => (
            <span key={t} className="rounded-full border border-hair px-2.5 py-0.5 text-[11px] text-ink-soft">
              {t}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
