'use client';

import { Line, LineChart, ResponsiveContainer } from 'recharts';
import type { NavChartPoint } from '@/lib/types';

/** Minimal NAV sparkline for overview (no axes). */
export function NavSparkline({ snaps }: { snaps: NavChartPoint[] }) {
  if (snaps.length < 2) return null;
  const data = snaps.map((s) => ({ nav: s.nav }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
        <Line
          type="monotone"
          dataKey="nav"
          stroke="#3b82f6"
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
