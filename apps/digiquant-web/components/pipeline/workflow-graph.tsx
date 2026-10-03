export type GraphNode = {
  label: string;
  /** Unfinished step. Drawn dashed so the picture does not read as shipped. */
  pending?: boolean;
};

/** One row of the picture. More than one node means those steps run together. */
export type GraphStep = {
  nodes: readonly GraphNode[];
};

function NodeBox({ node }: { node: GraphNode }) {
  return (
    <div
      className={
        "min-w-0 border px-2.5 py-1.5 font-mono text-[0.75rem] leading-[1.45] " +
        (node.pending ? "border-dashed border-hair text-ink-mute" : "border-hair text-ink")
      }
    >
      <span className="block">{node.label}</span>
    </div>
  );
}

/** A static picture of one workflow. Parallel steps sit on one row. Not a live run. */
export function WorkflowGraph({ label, steps }: { label: string; steps: readonly GraphStep[] }) {
  return (
    <figure className="m-0 flex flex-col gap-2 border-t border-hair pt-3">
      <figcaption className="font-mono text-[0.6875rem] tracking-[0.04em] text-ink-mute">graph · not a live run</figcaption>
      <ol aria-label={label} className="m-0 flex list-none flex-col gap-2 border-s border-hair ps-3">
        {steps.map((step) => {
          const parallel = step.nodes.length > 1;
          return (
            <li key={step.nodes.map((node) => node.label).join("|")} className="flex flex-col">
              {parallel ? (
                <div className="flex flex-col gap-1.5">
                  <span className="font-mono text-[0.6875rem] tracking-[0.04em] text-ink-mute">in parallel</span>
                  <ul aria-label="in parallel" className="m-0 grid list-none grid-cols-1 gap-2 p-0 sm:grid-cols-2 lg:grid-cols-3">
                    {step.nodes.map((node) => (
                      <li key={node.label} className="min-w-0">
                        <NodeBox node={node} />
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <NodeBox node={step.nodes[0]} />
              )}
            </li>
          );
        })}
      </ol>
    </figure>
  );
}
