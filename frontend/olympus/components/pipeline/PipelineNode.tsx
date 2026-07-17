'use client';

import { ChevronDown, ChevronRight, FileText, Info } from 'lucide-react';
import type { LaidOutNode } from '@/lib/pipeline-layout';

export interface PipelineNodeProps {
  node: LaidOutNode;
  count?: number;
  expandable?: boolean;
  expanded?: boolean;
  selected?: boolean;
  onActivate: () => void;
}

export default function PipelineNode({
  node,
  count,
  expandable = false,
  expanded = false,
  selected = false,
  onActivate,
}: PipelineNodeProps) {
  const isBranch = node.kind === 'fanout-branch';

  // Graph nodes use explicit flat-surface tokens instead of `.glass-card`:
  // MotionLayer mutates that class for page-level scroll reveals, which races
  // hydration and conflicts with transforms inside this custom camera.
  const cardClass = [
    'absolute',
    'transition-[border-color,box-shadow,transform] duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60',
    isBranch
      ? 'rounded-md border border-hair bg-term-bg'
      : 'rounded-lg border border-hair bg-surface',
    'cursor-pointer hover:-translate-y-px hover:border-hair-2',
    selected ? 'border-accent/60 shadow-[0_0_0_1px_var(--accent)]' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      role="button"
      tabIndex={0}
      aria-expanded={expandable ? expanded : undefined}
      aria-label={node.label}
      className={cardClass}
      style={{
        left: node.x,
        top: node.y,
        width: node.width,
        height: node.height,
      }}
      onClick={onActivate}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onActivate();
        }
      }}
    >
      <div className="flex items-center gap-1.5 px-3 h-full">
        {/* status pip — calm cyan recipe (F5): active when expanded, else
            border-subtle. No glow, no up/red chrome. */}
        <span
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            expanded ? 'bg-accent' : 'bg-hair'
          }`}
        />

        {/* label — stage = Geist Sans 13px medium; leaf/branch = Geist Mono 12px */}
        <span
          className={`flex-1 truncate leading-tight ${
            node.kind === 'stage'
              ? 'font-sans text-[13px] font-medium text-ink'
              : 'font-mono text-[12px] text-ink-soft'
          }`}
        >
          {node.label}
        </span>

        {/* count badge — accent chrome only, softened (no font-bold) */}
        {count != null && (
          <span className="font-mono text-[10px] tabular-nums text-accent bg-accent/15 rounded-full px-1.5 py-px flex-shrink-0">
            {count}
          </span>
        )}

        {/* expand chevron */}
        {expandable && (
          <span className="text-ink-mute flex-shrink-0">
            {expanded ? (
              <ChevronDown size={13} />
            ) : (
              <ChevronRight size={13} />
            )}
          </span>
        )}
        {!expandable && (
          <span className="flex-shrink-0 text-ink-mute" aria-hidden>
            {node.documentKey ? <FileText size={12} /> : <Info size={12} />}
          </span>
        )}
      </div>
    </div>
  );
}
