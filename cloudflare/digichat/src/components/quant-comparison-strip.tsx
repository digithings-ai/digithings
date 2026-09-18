"use client";

import { useMemo } from "react";
import type { UIMessage } from "ai";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@digithings/web/ui";

export type QuantMetricRow = {
  runId: string;
  strategy?: string;
  sharpe: number | null;
  totalReturnPct: number | null;
  maxDdPct: number | null;
  trades: number | null;
};

function scanForBacktestResults(
  v: unknown,
  out: QuantMetricRow[],
  seen: Set<string>
): void {
  if (!v || typeof v !== "object") return;
  const o = v as Record<string, unknown>;
  const runId = o.run_id;
  if (typeof runId === "string" && runId && !seen.has(runId)) {
    if ("sharpe_ratio" in o || "num_trades" in o) {
      seen.add(runId);
      const sr = o.sharpe_ratio;
      out.push({
        runId,
        strategy: typeof o.strategy_name === "string" ? o.strategy_name : undefined,
        sharpe:
          typeof sr === "number" ? sr : sr === null || sr === undefined ? null : null,
        totalReturnPct:
          typeof o.total_return_pct === "number" ? o.total_return_pct : null,
        maxDdPct:
          typeof o.max_drawdown_pct === "number" ? o.max_drawdown_pct : null,
        trades: typeof o.num_trades === "number" ? o.num_trades : null,
      });
    }
  }
  for (const k of Object.keys(o)) {
    scanForBacktestResults(o[k], out, seen);
  }
}

export function extractQuantMetricRows(messages: UIMessage[]): QuantMetricRow[] {
  const out: QuantMetricRow[] = [];
  const seen = new Set<string>();
  for (const m of messages) {
    if (m.role !== "assistant") continue;
    for (const p of m.parts ?? []) {
      scanForBacktestResults(p, out, seen);
    }
  }
  return out;
}

export function QuantComparisonStrip(props: {
  messages: UIMessage[];
  conversationId: string;
}) {
  const rows = useMemo(
    () => extractQuantMetricRows(props.messages),
    [props.messages]
  );

  if (rows.length < 1) return null;

  return (
    <Card className="mb-2 overflow-x-auto border-border/50 bg-term-bg p-3 text-xs">
      <div className="mb-2 font-medium text-muted-foreground">
        Quant runs in this thread ({rows.length})
      </div>
      <Table className="min-w-[480px] border-collapse text-left">
        <TableHeader>
          <TableRow className="border-border/40 text-muted-foreground hover:bg-transparent">
            <TableHead className="h-auto py-1 pr-2 pl-0 font-medium">Run</TableHead>
            <TableHead className="h-auto py-1 pr-2 pl-0 font-medium">Strategy</TableHead>
            <TableHead className="h-auto py-1 pr-2 pl-0 font-medium">Sharpe</TableHead>
            <TableHead className="h-auto py-1 pr-2 pl-0 font-medium">Ret %</TableHead>
            <TableHead className="h-auto py-1 pr-2 pl-0 font-medium">Max DD %</TableHead>
            <TableHead className="h-auto py-1 pl-0 font-medium">Trades</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.runId} className="border-border/20 hover:bg-transparent">
              <TableCell className="py-1 pr-2 pl-0 font-mono text-[10px] text-muted-foreground">
                {r.runId.slice(0, 12)}…
              </TableCell>
              <TableCell className="py-1 pr-2 pl-0">{r.strategy ?? "—"}</TableCell>
              <TableCell className="py-1 pr-2 pl-0">
                {r.sharpe === null ? "—" : r.sharpe.toFixed(3)}
              </TableCell>
              <TableCell className="py-1 pr-2 pl-0">
                {r.totalReturnPct === null ? "—" : r.totalReturnPct.toFixed(2)}
              </TableCell>
              <TableCell className="py-1 pr-2 pl-0">
                {r.maxDdPct === null ? "—" : r.maxDdPct.toFixed(2)}
              </TableCell>
              <TableCell className="py-1 pl-0">{r.trades ?? "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <p className="mt-2 text-[10px] text-muted-foreground">
        With Postgres enabled, persist runs via{" "}
        <span className="font-mono">POST /api/conversations/&lt;id&gt;/quant-runs</span>.
      </p>
    </Card>
  );
}
