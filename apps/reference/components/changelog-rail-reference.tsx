import { CardRail } from "@digithings/ui";
import { Badge, Card, CardContent } from "@digithings/ui/ui";

/**
 * Changelog rail — the specimen for the shared <CardRail/> (@digithings/ui):
 * a horizontal strip of release cards on native scroll-snap. Swipe, wheel, use
 * the arrow keys, or the prev / next buttons (one card per press); the edges
 * fade through tokens so the row reads as a strip rather than a cut-off grid.
 * Tags read by kind (feature · fix · breaking). Doubles as the sanctioned
 * mobile fallback for any band too wide to stack, and the rail digiquant's
 * tearsheets ride on.
 *
 * The rail mechanics (snap, fade, stepping, active mark) live in the kit part;
 * this file is only the demo cards. The release tag is the stock kit Badge —
 * feature → secondary, breaking → destructive, fix → outline — and the card is
 * the stock kit `Card`. The selected card (the one at the leading edge) is
 * `data-active` on its wrapper, so the card dresses it with a `group/card`
 * utility, no CSS.
 */
type Release = {
  version: string;
  date: string;
  title: string;
  entries: string[];
  tag: "feature" | "fix" | "breaking";
};

const RELEASES: Release[] = [
  {
    version: "v2.4",
    date: "2026-06-28",
    title: "Kelly-capped sizing",
    tag: "feature",
    entries: ["Position sizer honours a per-strategy Kelly cap.", "Flat-state guard on the momentum gate."],
  },
  {
    version: "v2.3",
    date: "2026-06-09",
    title: "Polars end to end",
    tag: "breaking",
    entries: ["Removed the legacy pandas resampler.", "Bar loaders now return Polars frames."],
  },
  {
    version: "v2.2",
    date: "2026-05-21",
    title: "Drawdown accounting",
    tag: "fix",
    entries: ["Fixed maxDD across session boundaries.", "Tearsheet PF matches the ledger."],
  },
  {
    version: "v2.1",
    date: "2026-05-02",
    title: "research loop",
    tag: "feature",
    entries: ["research proposes directions from free data.", "portfolio routes signals to the sizer."],
  },
  {
    version: "v2.0",
    date: "2026-04-14",
    title: "dashboard sub-graphs",
    tag: "breaking",
    entries: ["Split research / portfolio / execution into sub-graphs.", "Supervisor rewired around the split."],
  },
];

export function ChangelogRailReference() {
  return (
    <section className="section-block changelog-rail">
      <p className="kicker">{"// changelog rail"}</p>
      <h2 className="title">Content that scrolls sideways.</h2>
      <p className="section-copy">
        Changelog-class content lives on a horizontal rail: swipe it, wheel it, or use the arrows.
        Cards snap into place and the edges fade so the row reads as a strip, not a cut-off grid.
        This is also the sanctioned mobile fallback for any band too wide to stack.
      </p>

      <CardRail ariaLabel="Release notes, scrollable horizontally" className="mt-[1.2rem]">
        {RELEASES.map((rel) => (
          <Card
            key={rel.version}
            className="h-full select-none transition-colors group-data-[active=true]/card:border-accent"
          >
            <CardContent className="flex flex-col">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[0.95rem] text-ink">{rel.version}</span>
                <Badge
                  variant={
                    rel.tag === "breaking"
                      ? "destructive"
                      : rel.tag === "feature"
                        ? "secondary"
                        : "outline"
                  }
                >
                  {rel.tag}
                </Badge>
              </div>
              <p className="mt-[0.5rem] font-mono text-[0.62rem] tracking-[0.06em] text-ink-mute">{rel.date}</p>
              <h3 className="mt-[0.15rem] text-[1.05rem] text-ink">{rel.title}</h3>
              <ul className="mt-[0.7rem] grid list-none gap-[0.4rem] p-0">
                {rel.entries.map((entry) => (
                  <li
                    key={entry}
                    className="relative ps-4 text-[0.82rem] text-ink-soft before:absolute before:start-0 before:font-mono before:text-ink-mute before:content-['+']"
                  >
                    {entry}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ))}
      </CardRail>
    </section>
  );
}
