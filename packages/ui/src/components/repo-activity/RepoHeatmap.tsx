"use client";

import * as HeatGraph from "heat-graph";

import { bucketContributions, levelFor, type HeatDay } from "./heatmap";
import { grouped, type RepoPullItem } from "./types";

export type RepoHeatmapProps = {
  pulls: RepoPullItem[];
  /** Extra contribution sources: commit timestamps (ISO) and closed-issue timestamps (ISO). */
  commits?: Array<string | null | undefined>;
  closedIssues?: Array<string | null | undefined>;
  /** Pre-bucketed daily contributions (snapshot path). Overrides pulls/commits/issues when set. */
  data?: HeatDay[];
  /** Weeks of history, oldest week left. Defaults to 53 (a full year, GitHub-style). */
  weeks?: number;
  /** Window end (UTC day). Defaults to today. Test seam only. */
  end?: Date;
  /**
   * Grow the squares to fill the container instead of scrolling it. The cell
   * size is normally a fixed 10px and `.ra-heat-body` scrolls when the history
   * is wider than its column; with `fit` the grid takes 100% of the column and
   * each cell keeps a 1:1 aspect ratio, so the squares get bigger as the column
   * widens and smaller as it narrows — the count still picks how many weeks are
   * drawn (see `weeks`), the layout picks how large they are drawn.
   */
  fit?: boolean;
  className?: string;
};

/**
 * RepoHeatmap — repo-level contributions over the last year, GitHub
 * profile-graph style, via assistant-ui's headless `heat-graph`.
 * DigiWeb livery: perfect squares (no radius), categorical accent steps
 * via `var(--accent)` — flat fills only, no gradients. Month row on top,
 * Mon/Wed/Fri day labels, Less/More legend, per-cell title tooltip.
 */
const COLOR_SCALE = [
  "color-mix(in srgb, var(--ink) 9%, transparent)",
  "color-mix(in srgb, var(--accent) 28%, transparent)",
  "color-mix(in srgb, var(--accent) 52%, transparent)",
  "color-mix(in srgb, var(--accent) 76%, transparent)",
  "var(--accent)",
];

const DAY_LABELS = new Set(["Mon", "Wed", "Fri"]);

/**
 * Hover text for one square. States the day, the total, and — when the caller
 * bucketed the sources — the split behind it, because "5 contributions" and
 * "5 commits" are different facts and the graph alone cannot tell them apart.
 */
function cellTitle(date: string, count: number, day: HeatDay | undefined): string {
  const noun = count === 1 ? "contribution" : "contributions";
  if (day && (day.commits != null || day.pulls != null || day.issues != null)) {
    const parts: string[] = [];
    if (day.commits) parts.push(`${day.commits} commit${day.commits === 1 ? "" : "s"}`);
    if (day.pulls) parts.push(`${day.pulls} PR${day.pulls === 1 ? "" : "s"}`);
    if (day.issues) parts.push(`${day.issues} issue${day.issues === 1 ? "" : "s"}`);
    if (parts.length) return `${date} — ${count} ${noun}: ${parts.join(", ")}`;
  }
  return `${date} — ${count} ${noun}`;
}

export function RepoHeatmap({
  pulls,
  commits = [],
  closedIssues = [],
  data,
  weeks = 53,
  end,
  fit = false,
  className,
}: RepoHeatmapProps) {
  const days: HeatDay[] =
    data ?? bucketContributions(pulls, commits, closedIssues, weeks, end ?? new Date());
  const total = days.reduce((m, d) => m + d.count, 0);
  const cls = ["ra-heat", fit ? "ra-heat--fit" : "", className ?? ""].filter(Boolean).join(" ");
  const range = weeks >= 50 ? "the last year" : `the last ${weeks} weeks`;
  const points = days.map((d) => ({ date: d.date, count: d.count }));
  // The grid hands back its own cells, so the per-day split is looked up by
  // date to build the hover title.
  const byDate = new Map(days.map((d) => [d.date, d]));

  return (
    <div className={cls}>
      <p className="ra-heat-total">
        {grouped(total)} contributions in {range}
      </p>
      <HeatGraph.Root
        data={points}
        start={days[0]?.date ?? points[0]?.date}
        end={days[days.length - 1]?.date ?? new Date()}
        weekStart="sunday"
        colorScale={COLOR_SCALE}
        classify={(counts) => {
          const max = counts.reduce((m, c) => Math.max(m, c), 0);
          return (count: number) => levelFor(count, max);
        }}
        className="ra-heat-graph"
        role="img"
        aria-label={`${grouped(total)} contributions in ${range}.`}
      >
        <div className="ra-heat-body">
          {/* One max-content frame holds the month row, the cell row and the
              legend, so the month-label coordinate space is exactly the grid
              width. Without it .ra-heat-months spans the full body width while
              .ra-heat-grid is only max-content wide, and the %-positioned
              labels drift right of their columns (last label ~172px past the
              last cell at 1440). The frame is max-content at every viewport;
              .ra-heat-body scrolls when it does not fit. */}
          <div className="ra-heat-frame">
            <div className="ra-heat-months" aria-hidden="true">
              <HeatGraph.MonthLabels>
                {({ label, totalWeeks }) => (
                  <span
                    key={`${label.month}-${label.column}`}
                    className="ra-heat-month"
                    style={{ left: `${(label.column / totalWeeks) * 100}%` }}
                  >
                    {HeatGraph.MONTH_SHORT[label.month]}
                  </span>
                )}
              </HeatGraph.MonthLabels>
            </div>
            <div className="ra-heat-row">
              <div className="ra-heat-days" aria-hidden="true">
                <HeatGraph.DayLabels>
                  {({ label }) => {
                    const name = HeatGraph.DAY_SHORT[label.dayOfWeek];
                    if (!DAY_LABELS.has(name))
                      return <span key={label.row} className="ra-heat-day" />;
                    return (
                      <span key={label.row} className="ra-heat-day">
                        {name}
                      </span>
                    );
                  }}
                </HeatGraph.DayLabels>
              </div>
              <HeatGraph.Grid className="ra-heat-grid">
                {({ cell }) => {
                  const date = cell.date.toISOString().slice(0, 10);
                  const n = cell.count;
                  return (
                    <HeatGraph.Cell
                      key={`${cell.column}-${cell.row}`}
                      className="ra-heat-cell"
                      data-level={cell.level}
                      title={cellTitle(date, n, byDate.get(date))}
                    />
                  );
                }}
              </HeatGraph.Grid>
            </div>
            <div className="ra-heat-foot">
              <span />
              <div className="ra-heat-legend" aria-hidden="true">
                <span>Less</span>
                <HeatGraph.Legend>
                  {() => <HeatGraph.LegendLevel className="ra-heat-cell" />}
                </HeatGraph.Legend>
                <span>More</span>
              </div>
            </div>
          </div>
        </div>
      </HeatGraph.Root>
    </div>
  );
}
