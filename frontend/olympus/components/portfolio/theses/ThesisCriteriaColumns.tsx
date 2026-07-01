'use client';

import { Check, X } from 'lucide-react';

function CriteriaList({
  title,
  items,
  tone,
  emptyLabel,
}: {
  title: string;
  items: string[];
  tone: 'confirm' | 'break';
  emptyLabel: string;
}) {
  const accent = tone === 'confirm' ? 'text-fin-green' : 'text-fin-red';
  const Icon = tone === 'confirm' ? Check : X;
  return (
    <div className="glass-card p-5">
      <h3 className="mb-4 text-sm font-semibold text-text-primary">{title}</h3>
      {items.length === 0 ? (
        <p className="text-xs text-text-muted">{emptyLabel}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-3 text-sm leading-relaxed text-text-secondary">
              <Icon size={15} className={`mt-0.5 shrink-0 ${accent}`} aria-hidden />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ThesisCriteriaColumns({
  validation,
  invalidation,
}: {
  validation: string[];
  invalidation: string[];
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <CriteriaList
        title="What confirms this"
        items={validation}
        tone="confirm"
        emptyLabel="No confirmation criteria recorded for this thesis yet."
      />
      <CriteriaList
        title="What breaks this"
        items={invalidation}
        tone="break"
        emptyLabel="No invalidation criteria recorded for this thesis yet."
      />
    </div>
  );
}
