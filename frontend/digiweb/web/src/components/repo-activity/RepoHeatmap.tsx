import { bucketDaily, levelFor, type HeatDay } from "./heatmap";
import { grouped, type RepoPullItem } from "./types";

export type RepoHeatmapProps = {
  pulls: RepoPullItem[];
  /** Weeks of history, oldest week left. Defaults to 16 (~four months). */
  weeks?: number;
  /** Window end (UTC day). Defaults to today. Test seam only. */
  end?: Date;
  className?: string;
};

/**
 * RepoHeatmap — merge heat over the last N weeks, derived from
 * `mergedPulls[].mergedAt` with no snapshot change. Weeks are columns,
 * oldest left; every cell a perfect square, no radius, no borders.
 * Accent steps follow the one-livery rule via `var(--accent)`.
 */
export function RepoHeatmap({ pulls, weeks = 16, end, className }: RepoHeatmapProps) {
  const days: HeatDay[] = bucketDaily(pulls, weeks, end);
  const max = days.reduce((m, d) => Math.max(m, d.count), 0);
  const total = days.reduce((m, d) => m + d.count, 0);
  const displayWeeks = days.length / 7;
  const cls = ["ra-heat", className ?? ""].filter(Boolean).join(" ");

  return (
    <div
      className={cls}
      role="img"
      aria-label={`Merge heat: ${grouped(total)} merged pull request${total === 1 ? "" : "s"} over the last ${displayWeeks} week${displayWeeks === 1 ? "" : "s"}.`}
    >
      {days.map((d) => (
        <span
          key={d.date}
          className="ra-heat-cell"
          data-level={levelFor(d.count, max)}
          title={`${d.date} — ${d.count} merge${d.count === 1 ? "" : "s"}`}
        />
      ))}
    </div>
  );
}
