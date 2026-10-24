import { ReleaseRail, type ReleaseRailItem } from "@digithings/ui";

/**
 * Release rail — the changelog's row grammar: one bordered row per release, the
 * version, date and product pinned in a sticky aside, the shipped title and its
 * highlights in the wide column. Static, so the changelog reads without
 * JavaScript. This is the digithings.ai `/changelog` composition (D1, #4429),
 * replacing the released `.cr-card` scroll strip for long-form lists. Static
 * display template.
 */
const RELEASES: ReleaseRailItem[] = [
  {
    product: "digichat",
    version: "v2.3.1",
    date: "2026-09-20",
    tag: "fix",
    title: "Charge the free-turn counter at send time",
    href: "https://github.com/digithings-ai/digithings/releases/tag/digichat-v2.3.1",
    entries: ["The embed counter no longer lags one turn behind the transcript."],
  },
  {
    product: "digichat",
    version: "v2.3.0",
    date: "2026-09-19",
    title: "Theme handoff without a reload",
    href: "https://github.com/digithings-ai/digithings/releases/tag/digichat-v2.3.0",
    entries: ["The embedded app follows the parent theme live.", "Boot loader holds the shell."],
  },
  {
    product: "digiskills",
    version: "v0.2.1",
    date: "2026-08-15",
    title: "Skill packaging fixes",
    href: "https://github.com/digithings-ai/digithings/releases/tag/digiskills-v0.2.1",
  },
];

export function ReleaseRailReference() {
  return (
    <section className="section-block" id="release-rail">
      <p className="kicker">{"// release rail"}</p>
      <h2 className="title">Dated rows, sticky versions.</h2>
      <p className="section-copy">
        Every release is a bordered row: `180px` for the version, date and product, the remainder
        for what shipped. The aside stays put while a long entry scrolls past, and the rows read
        as one ledger rather than a stack of cards.
      </p>
      <div className="mt-[1.2rem]">
        <ReleaseRail items={RELEASES} />
      </div>
    </section>
  );
}
