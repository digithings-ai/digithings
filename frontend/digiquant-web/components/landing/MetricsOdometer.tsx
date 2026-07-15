"use client";
/** Homepage odometer strip (#1069). The "backtested trades" figure is summed
 *  live from the Supabase strategy index — every number here is mined from
 *  shipped data, never invented. The other three are structural constants. */
import { useEffect, useState } from "react";
import { OdometerStrip, type OdometerStat } from "@digithings/web";
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
    { value: "7", label: "pipeline stages" },
    { value: String(trades), label: "backtested trades" },
    { value: "0", label: "ungated live orders" },
  ];

  return <OdometerStrip stats={stats} className={className} />;
}
