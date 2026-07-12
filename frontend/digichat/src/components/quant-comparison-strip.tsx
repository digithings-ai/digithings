"use client";

import { useMemo } from "react";
import type { UIMessage } from "ai";
import { Card } from "@/components/ui/card";

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
      <table className="w-full min-w-[480px] border-collapse text-left">
        <thead>
          <tr className="border-b border-border/40 text-muted-foreground">
            <th className="py-1 pr-2 font-medium">Run</th>
            <th className="py-1 pr-2 font-medium">Strategy</th>
            <th className="py-1 pr-2 font-medium">Sharpe</th>
            <th className="py-1 pr-2 font-medium">Ret %</th>
            <th className="py-1 pr-2 font-medium">Max DD %</th>
            <th className="py-1 font-medium">Trades</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.runId} className="border-b border-border/20">
              <td className="py-1 pr-2 font-mono text-[10px] text-muted-foreground">
                {r.runId.slice(0, 12)}…
              </td>
              <td className="py-1 pr-2">{r.strategy ?? "—"}</td>
              <td className="py-1 pr-2">
                {r.sharpe === null ? "—" : r.sharpe.toFixed(3)}
              </td>
              <td className="py-1 pr-2">
                {r.totalReturnPct === null ? "—" : r.totalReturnPct.toFixed(2)}
              </td>
              <td className="py-1 pr-2">
                {r.maxDdPct === null ? "—" : r.maxDdPct.toFixed(2)}
              </td>
              <td className="py-1">{r.trades ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[10px] text-muted-foreground">
        With Postgres enabled, persist runs via{" "}
        <span className="font-mono">POST /api/conversations/&lt;id&gt;/quant-runs</span>.
      </p>
    </Card>
  );
}
