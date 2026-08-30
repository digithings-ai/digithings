'use client';

import { AlertTriangle, ChevronDown, ChevronRight, CircleDashed, FileText, GitFork, Info } from 'lucide-react';
import { pipelineNodeRunStatusLabel } from '@/lib/pipeline-layout';
import type { LaidOutNode, PipelineNodeRunStatus } from '@/lib/pipeline-layout';

export interface PipelineNodeProps {
  node: LaidOutNode;
  count?: number;
  expandable?: boolean;
  expanded?: boolean;
  selected?: boolean;
  onActivate: () => void;
}

function resolvedStatus(node: LaidOutNode): PipelineNodeRunStatus {
  if (node.runStatus) return node.runStatus;
  if (node.documentKey) return 'persisted-artifact';
  if (node.stateOnly) return 'state-only';
  return node.kind === 'stage' ? 'stage-overview' : 'not-run';
}

function statusPipClass(status: PipelineNodeRunStatus, expanded: boolean): string {
  if (status === 'expected-artifact-missing') return 'bg-warn';
  if (status === 'persisted-artifact' || status === 'parallel-dispatch') return 'bg-accent';
  if (status === 'state-only') return 'border border-accent/70 bg-transparent';
  if (status === 'stage-overview' && expanded) return 'bg-accent';
  return 'bg-hair';
}

function StatusIcon({ status }: { status: PipelineNodeRunStatus }) {
  if (status === 'persisted-artifact') return <FileText size={12} />;
  if (status === 'expected-artifact-missing') return <AlertTriangle size={12} />;
  if (status === 'parallel-dispatch') return <GitFork size={12} />;
  if (status === 'not-run') return <CircleDashed size={12} />;
  return <Info size={12} />;
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
  const status = resolvedStatus(node);
  const statusLabel = pipelineNodeRunStatusLabel(status);

  // Graph nodes use explicit flat-surface tokens instead of `.oly-slab`:
  // MotionLayer mutates that class for page-level scroll reveals, which races
  // hydration and conflicts with transforms inside this custom camera.
  const cardClass = [
    'absolute',
    'transition-[border-color,box-shadow,transform] duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60',
    isBranch
      ? 'border border-hair bg-term-bg'
      : 'border border-hair bg-surface',
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
      aria-label={`${node.label}, ${statusLabel}`}
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
          title={statusLabel}
          className={`h-2 w-2 flex-shrink-0 rounded-full ${statusPipClass(status, expanded)}`}
        />

        {/* label — stage = Geist Sans 13px medium; leaf/branch = Geist Mono 12px */}
        <span
          className={`flex-1 truncate leading-tight ${
            node.kind === 'stage'
              ? 'font-sans text-sm font-medium text-ink'
              : 'font-mono text-xs text-ink-soft'
          }`}
        >
          {node.label}
        </span>

        {/* count badge — accent chrome only, softened (no font-bold) */}
        {count != null && (
          <span className="flex-shrink-0 rounded-full bg-accent/15 px-1.5 py-px font-mono text-xs tabular-nums text-accent">
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
          <span className="flex-shrink-0 text-ink-mute" title={statusLabel} aria-hidden>
            <StatusIcon status={status} />
          </span>
        )}
      </div>
    </div>
  );
}
