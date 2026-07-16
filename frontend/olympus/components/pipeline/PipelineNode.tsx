'use client';

import { ChevronDown, ChevronRight } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@digithings/web';
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

  // A leaf substep/branch with no documentKey and nothing to expand can never
  // open anything (PipelineCanvas.handleNodeClick no-ops on a missing
  // documentKey) — render it visibly inert instead of looking identical to a
  // real, clickable node (#1259 follow-up: a PM couldn't tell "no data today"
  // from "broken"). State-only steps (thesis, screener, consolidate, preflight)
  // are inert EVERY day by design — say so instead of the misleading
  // "no output today" (#1538).
  const isInert = !expandable && !node.documentKey;
  const inertTitle = node.stateOnly
    ? 'Runs in pipeline state only — never publishes a document'
    : 'No output for this step on this day';

  // Branches read as nested cards: recessed inset + tighter 6px radius. Standard
  // nodes use the shared .glass-card primitive (flat panel, 8px radius, hover
  // border-glow). Decision is NOT special-cased (F5 — no green chrome).
  const cardClass = [
    'absolute',
    'transition-[border-color,box-shadow,transform] duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60',
    isBranch ? 'rounded-md border border-hair bg-term-bg' : 'glass-card',
    isInert
      ? 'cursor-default'
      : `cursor-pointer hover:-translate-y-px${isBranch ? ' hover:border-hair-2' : ''}`,
    selected ? 'border-accent/60 shadow-[0_0_0_1px_var(--accent)]' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const card = (
    <div
      role="button"
      tabIndex={isInert ? -1 : 0}
      aria-disabled={isInert || undefined}
      aria-expanded={expandable ? expanded : undefined}
      aria-label={node.label}
      className={cardClass}
      style={{
        left: node.x,
        top: node.y,
        width: node.width,
        height: node.height,
        // Inline, not a Tailwind class — `.glass-card.reveal-in` (the mount
        // reveal-animation rule, app/globals.css) sets `opacity: 1` with
        // higher specificity than a plain utility class, so `opacity-50`
        // would get silently overridden once the reveal transition settles.
        opacity: isInert ? 0.5 : undefined,
      }}
      onClick={isInert ? undefined : onActivate}
      onKeyDown={
        isInert
          ? undefined
          : (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onActivate();
              }
            }
      }
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
      </div>
    </div>
  );

  if (!isInert) return card;

  // Inert nodes explain themselves via the promoted @digithings/web Tooltip
  // (hover + focus + touch, token-themed) instead of a native title= bubble.
  return (
    <TooltipProvider delay={200}>
      <Tooltip>
        <TooltipTrigger render={card} />
        <TooltipContent side="bottom">{inertTitle}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
