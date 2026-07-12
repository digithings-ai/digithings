'use client';

import type { ReactNode } from 'react';
import { FileText } from 'lucide-react';
import LibraryDocumentBody from '@/components/library/LibraryDocumentBody';
import type { LibraryDocumentResult } from '@/lib/queries';

export default function DocumentExpandInline(props: {
  accent?: 'blue' | 'amber';
  /** When false, omit title row — use when the parent row already shows the document name. */
  hideTitleBar?: boolean;
  title: string;
  subtitle?: string | null;
  badge?: ReactNode;
  loading: boolean;
  libraryDoc: LibraryDocumentResult | null;
}) {
  const { accent = 'blue', hideTitleBar = false, title, subtitle, badge, loading, libraryDoc } = props;
  const tint =
    accent === 'amber'
      ? 'border-warn/20 bg-warn/[0.03]'
      : 'border-accent/15 bg-term-bg/30';
  const iconClass = accent === 'amber' ? 'text-warn shrink-0' : 'text-accent shrink-0';

  return (
    <div className={`border-t border-hair ${tint}`}>
      {!hideTitleBar ? (
        <div className="flex items-center gap-3 px-5 py-2.5 bg-term-bg/70">
          <div className="flex items-center gap-2 min-w-0 text-sm">
            <FileText size={14} className={iconClass} aria-hidden />
            <span className="font-mono truncate">{title}</span>
            {subtitle ? (
              <span className="text-[11px] text-ink-mute font-mono shrink-0" title="Document date">
                {subtitle}
              </span>
            ) : null}
            {badge}
          </div>
        </div>
      ) : null}
      <div
        className={`px-5 pb-5 max-w-none text-sm leading-relaxed overflow-auto max-h-[min(70vh,800px)] ${
          hideTitleBar ? 'pt-3' : 'pt-2'
        }`}
      >
        {loading || !libraryDoc ? (
          <div className="text-ink-soft text-sm py-4">Loading document…</div>
        ) : (
          <LibraryDocumentBody
            view={libraryDoc.view}
            markdown={libraryDoc.markdown}
            payload={libraryDoc.payload}
            documentKey={libraryDoc.document_key}
            docDate={libraryDoc.date}
          />
        )}
      </div>
    </div>
  );
}
