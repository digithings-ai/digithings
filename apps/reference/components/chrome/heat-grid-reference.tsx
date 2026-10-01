"use client";

/**
 * HeatGrid + CalendarHeatmap specimen — stepped-tone SVG intensity grids.
 * HeatGrid is a rows x cols matrix, sequential or diverging (health palette
 * accent/warn by default, `pnl` for up/down). CalendarHeatmap places days in
 * week columns and takes a `unit` noun; it reuses the RepoHeatmap level steps.
 */
import { CalendarHeatmap, HeatGrid } from "@digithings/ui/ui";

const CCY = ["USD", "EUR", "GBP", "JPY"];
const CORR = [
  [1, 0.42, 0.31, -0.55],
  [0.42, 1, 0.64, -0.2],
  [0.31, 0.64, 1, null],
  [-0.55, -0.2, null, 1],
];
const EVENTS = [
  [0, 3, 5, 1, 2],
  [1, 0, 2, 6, 4],
  [4, 2, 0, 1, null],
];

function days(): Array<{ date: string; count: number }> {
  const out: Array<{ date: string; count: number }> = [];
  const start = Date.UTC(2026, 5, 1);
  for (let i = 0; i < 120; i++) {
    const date = new Date(start + i * 86_400_000).toISOString().slice(0, 10);
    out.push({ date, count: (i * 7 + (i % 5) * 3) % 9 > 5 ? 0 : (i * 5) % 8 });
  }
  return out;
}

export function HeatGridReference() {
  return (
    <section className="section-block" id="heat-grid">
      <p className="kicker">{"// heat-grid"}</p>
      <h2 className="title">Intensity, on a stepped scale.</h2>
      <p className="section-copy">
        <code>HeatGrid</code> and <code>CalendarHeatmap</code> from <code>@digithings/ui</code>.
        Five flat steps, no gradients; missing cells draw a hairline outline.
      </p>

      <div className="mt-[1.2rem] grid gap-[1.2rem] border border-hair p-[1.2rem]">
        <div>
          <p className="kicker">{"// diverging (health palette)"}</p>
          <HeatGrid rows={CCY} cols={CCY} values={CORR} scale="diverging" domain={[-1, 1]} showValues />
        </div>
        <div>
          <p className="kicker">{"// sequential: event density"}</p>
          <HeatGrid
            rows={["Mon", "Tue", "Wed"]}
            cols={["Asia", "London", "NY", "Close", "Late"]}
            values={EVENTS}
            cellWidth={48}
          />
        </div>
        <div>
          <p className="kicker">{"// calendar, unit = docs"}</p>
          <CalendarHeatmap days={days()} unit={{ singular: "doc", plural: "docs" }} />
        </div>
      </div>
    </section>
  );
}
