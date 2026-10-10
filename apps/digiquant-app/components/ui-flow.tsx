import type { ReactNode } from 'react';

/** Stepper: numbered steps with a state each. Used by deploy flow, run progress. */
export type Step = { label: string; state: 'done' | 'active' | 'todo' | 'failed'; detail?: ReactNode };
export function Stepper({ steps }: { steps: Step[] }) {
  return (
    <ol className="steps">
      {steps.map((s, i) => (
        <li key={`${s.label}:${i}`} className={`step ${s.state}`} aria-current={s.state === 'active' ? 'step' : undefined}>
          <span className="step-n mono">{i + 1}</span>
          <span className="step-b">
            <span className="step-l">{s.label}</span>
            {s.detail ? <span className="step-d">{s.detail}</span> : null}
          </span>
        </li>
      ))}
    </ol>
  );
}

/**
 * FlowGraph: pipeline nodes in columns by `col`, edges listed under each node as
 * "→ target". Deliberately DOM, not SVG-with-coordinates, so it reflows and zooms.
 */
export type FlowNodeData = { id: string; label: string; col: number; state?: 'ok' | 'running' | 'failed' | 'idle' | 'skipped'; meta?: string; to?: string[] };
export function FlowGraph({ nodes, onSelect, selected }: { nodes: FlowNodeData[]; onSelect?: (id: string) => void; selected?: string | null }) {
  const cols = [...new Set(nodes.map((n) => n.col))].sort((a, b) => a - b);
  return (
    <div className="flow" role="group" aria-label="Pipeline graph">
      {cols.map((c) => (
        <div className="flow-col" key={c}>
          {nodes.filter((n) => n.col === c).map((n) => (
            <button
              key={n.id}
              type="button"
              className={`fnode ${n.state ?? 'idle'}${selected === n.id ? ' on' : ''}`}
              onClick={() => onSelect?.(n.id)}
              aria-pressed={selected === n.id}
            >
              <span className="fnode-l">{n.label}</span>
              {n.meta ? <span className="fnode-m">{n.meta}</span> : null}
              {n.to?.length ? <span className="fnode-e">→ {n.to.join(' ')}</span> : null}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
