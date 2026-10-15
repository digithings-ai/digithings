"use client";

/**
 * Pipeline flow — a signal travelling down one example orchestration.
 *
 * No legend, no notes column, no receipt. The shape of the pipeline (how many
 * stages, which ones run in parallel) already tells the story; motion is a
 * continuous cascading pulse down the conduit between stages, staggered by
 * depth, so every card reads differently without any per-card wiring.
 */

import { useMotionSafe } from "@digithings/ui";

export type FlowNode = {
  label: string;
  pending?: boolean;
  tone?: "main" | "model" | "side" | "fallback";
};

/** One row of the picture. More than one node means those steps run together. */
export type FlowStep = {
  nodes: readonly FlowNode[];
};

function nodeTone(node: FlowNode): "main" | "model" | "side" | "fallback" | "pending" {
  if (node.pending) return "pending";
  return node.tone ?? "side";
}

export function PipelineFlow({
  label,
  steps,
  loop,
}: {
  label: string;
  steps: readonly FlowStep[];
  loop: string;
}) {
  const safe = useMotionSafe();
  return (
    <figure className="pflow" data-motion={safe ? "on" : "off"} aria-label={`${label}. not a live run`}>
      <ol className="pflow__chain">
        {steps.map((step, index) => {
          const parallel = step.nodes.length > 1;
          const pending = step.nodes.every((node) => node.pending);
          return (
            <li key={step.nodes.map((node) => node.label).join("|")} className="pflow__stage">
              {index > 0 ? (
                <span className="pflow__conduit" data-pending={pending} aria-hidden="true" style={{ "--pflow-i": index } as never}>
                  <span className="pflow__pulse" />
                </span>
              ) : null}
              <div className="pflow__nodes" data-parallel={parallel}>
                {parallel ? <span className="pflow__bus">in parallel</span> : null}
                {step.nodes.map((node) => (
                  <span key={node.label} className="pflow__node" data-tone={nodeTone(node)}>
                    {node.label}
                  </span>
                ))}
              </div>
            </li>
          );
        })}
      </ol>
      <p className="pflow__loop">
        <span className="pflow__loop-arc" aria-hidden="true" />
        {loop}
      </p>
    </figure>
  );
}
