"use client";
/** Homepage odometer strip (#1069). Every number here is mined from a shipped
 *  source, never hand-written: the subsystem count from the shared registry
 *  (passed in), the phase count from the single pipeline data file
 *  (`app/_pipeline.ts`, the same file the chip gallery reads), the zero as the
 *  named `LIVE_ORDERS` constant, and the trade count summed live from the
 *  Supabase strategy index. */
import { useEffect, useState } from "react";
import { OdometerStrip, type OdometerStat } from "@digithings/ui";
import { LIVE_ORDERS, PIPELINE_PHASES } from "@/app/_pipeline";
import { fetchStrategyIndex } from "@/lib/live/strategies";

export function MetricsOdometer({
  subsystemCount,
  className,
}: {
  subsystemCount: number;
  className?: string;
}) {
  const [trades, setTrades] = useState(0);

  useEffect(() => {
    let alive = true;
    void fetchStrategyIndex().then((all) => {
      if (alive) setTrades(all.reduce((n, s) => n + s.total_trades, 0));
    });
    return () => {
      alive = false;
    };
  }, []);

  const stats: OdometerStat[] = [
    { value: String(subsystemCount), label: "subsystems" },
    { value: String(PIPELINE_PHASES.length), label: "pipeline phases" },
    { value: String(trades), label: "backtested trades" },
    { value: String(LIVE_ORDERS), label: "live orders" },
  ];

  return <OdometerStrip stats={stats} className={className} />;
}
