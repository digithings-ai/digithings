'use client';

import { ChevronDown, ChevronRight } from 'lucide-react';
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

  // Branches read as nested cards: recessed inset + tighter 6px radius. Standard
  // nodes use the shared .glass-card primitive (flat panel, 8px radius, hover
  // border-glow). Decision is NOT special-cased (F5 — no green chrome).
  const cardClass = [
    'absolute cursor-pointer',
    'transition-[border-color,box-shadow,transform] duration-150',
    'hover:-translate-y-px',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fin-blue/60',
    isBranch
      ? 'rounded-md border border-border-subtle bg-bg-secondary hover:border-border-glow'
      : 'glass-card',
    selected ? 'border-fin-blue/60 shadow-[0_0_0_1px_var(--color-fin-blue)]' : '',
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
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onActivate();
        }
      }}
    >
      <div className="flex items-center gap-1.5 px-3 h-full">
        {/* status pip — calm cyan recipe (F5): active when expanded, else
            border-subtle. No glow, no fin-green/red chrome. */}
        <span
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            expanded ? 'bg-fin-blue' : 'bg-border-subtle'
          }`}
        />

        {/* label — stage = Geist Sans 13px medium; leaf/branch = Geist Mono 12px */}
        <span
          className={`flex-1 truncate leading-tight ${
            node.kind === 'stage'
              ? 'font-sans text-[13px] font-medium text-text-primary'
              : 'font-mono text-[12px] text-text-secondary'
          }`}
        >
          {node.label}
        </span>

        {/* count badge — accent chrome only, softened (no font-bold) */}
        {count != null && (
          <span className="font-mono text-[10px] tabular-nums text-fin-blue bg-fin-blue/15 rounded-full px-1.5 py-px flex-shrink-0">
            {count}
          </span>
        )}

        {/* expand chevron */}
        {expandable && (
          <span className="text-text-muted flex-shrink-0">
            {expanded ? (
              <ChevronDown size={13} />
            ) : (
              <ChevronRight size={13} />
            )}
          </span>
        )}
      </div>
    </div>
  );
}
