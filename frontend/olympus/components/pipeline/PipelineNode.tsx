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
  const isDecision = node.stageId === 'decision' && node.kind === 'stage';
  const isBranch = node.kind === 'fanout-branch';

  let borderClass = 'border-border';
  if (selected) borderClass = 'border-fin-blue';
  else if (isDecision) borderClass = 'border-fin-green/45';

  const cardClass = [
    'absolute rounded-xl border backdrop-blur-md cursor-pointer',
    'transition-[border-color,box-shadow,transform] duration-150',
    'hover:-translate-y-px hover:shadow-lg hover:border-fin-blue/55',
    isBranch ? 'bg-[var(--panel)] text-[length:var(--text-sm)]' : 'bg-glass',
    borderClass,
    selected ? 'shadow-[0_0_0_1px_var(--color-fin-blue)]' : '',
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
        {/* status dot */}
        <span
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            isDecision
              ? 'bg-fin-green shadow-[0_0_8px_var(--color-fin-green)]'
              : node.kind === 'fanout-branch'
                ? 'bg-fin-blue'
                : 'bg-fin-green'
          }`}
        />

        {/* label */}
        <span className="text-[13px] font-semibold tracking-tight leading-tight flex-1 truncate">
          {node.label}
        </span>

        {/* count badge — accent only */}
        {count != null && (
          <span className="text-[10px] font-bold text-fin-blue bg-fin-blue/10 rounded-full px-1.5 py-px flex-shrink-0">
            {count}
          </span>
        )}

        {/* expand chevron */}
        {expandable && (
          <span className="text-muted flex-shrink-0">
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
