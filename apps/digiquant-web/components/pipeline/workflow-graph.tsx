import {
  TerminalSchematic,
  type SchematicLegend,
  type SchematicNode,
  type SchematicRow,
  type SchematicTone,
} from "@digithings/ui";

export type GraphNode = {
  label: string;
  /** Unfinished step. Stays pending — the picture does not call it shipped. */
  pending?: boolean;
  tone?: Exclude<SchematicTone, "pending">;
};

/** One row of the picture. More than one node means those steps run together. */
export type GraphStep = {
  nodes: readonly GraphNode[];
};

const LEGEND_LABEL: Record<SchematicLegend["tone"], string> = {
  main: "main step",
  model: "model step",
  side: "side step",
  fallback: "fallback",
  ok: "ok",
  pending: "pending",
};

function nodeTone(node: GraphNode): SchematicTone {
  if (node.pending) return "pending";
  return node.tone ?? "side";
}

function legendFor(rows: readonly SchematicRow[]): SchematicLegend[] {
  const used = new Set<SchematicLegend["tone"]>(["ok"]);
  for (const row of rows) {
    for (const node of row.nodes) used.add(node.tone);
  }
  const order: SchematicLegend["tone"][] = ["main", "model", "side", "fallback", "ok", "pending"];
  return order.filter((tone) => used.has(tone)).map((tone) => ({ tone, label: LEGEND_LABEL[tone] }));
}

/** A terminal picture of one workflow. Parallel steps share a row. Not a live run. */
export function WorkflowGraph({
  label,
  steps,
  loop,
  notes,
  receipt,
}: {
  label: string;
  steps: readonly GraphStep[];
  loop: string;
  notes: readonly string[];
  receipt: readonly string[];
}) {
  const rows: SchematicRow[] = steps.map((step) => ({
    nodes: step.nodes.map((node) => ({ label: node.label, tone: nodeTone(node) })),
  }));
  return (
    <TerminalSchematic
      title={label}
      label={`${label}. not a live run`}
      rows={rows}
      loop={loop}
      notes={notes}
      receipt={receipt}
      legend={legendFor(rows)}
    />
  );
}
