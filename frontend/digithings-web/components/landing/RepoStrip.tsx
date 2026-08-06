import { GitHubGlyph } from "@digithings/web";
import { REPO_URL, grouped, isoDay, repoActivity } from "@/lib/repoActivity";

/**
 * The hairline band directly under the hero — what used to be a drifting
 * <Marquee> of vendor logos.
 *
 * The marquee was replaced rather than restyled: it named the same seven
 * dependencies the #integrations section names deliberately and in full, so it
 * carried no information the page did not already give, and it paid for that with
 * perpetual motion under the hero. This band occupies the same slot and the same
 * visual weight, and spends it on something a visitor cannot get anywhere else on
 * the page — evidence the repository is alive.
 *
 * Every figure comes from the committed snapshot, and the band prints the snapshot's
 * own date so a stale number reads as dated rather than as current.
 *
 * Two rows, and the split is semantic rather than cosmetic: row one is what moved in
 * the last 30 days, row two is what is true right now. Issues closed sits at the end
 * of row one and issues open at the start of row two — adjacent in reading order,
 * because the pair is the point (151 closed alone is a boast, 197 open alone is an
 * indictment, together it is a backlog being worked), but separately scoped, because
 * they are not the same measurement. See the generator's docstring.
 *
 * Server component — the data is inlined at build, so there is no fetch, no
 * loading state and no failure mode.
 */
export function RepoStrip() {
  const a = repoActivity;
  const n = (v: number) => <span className="text-ink">{grouped(v)}</span>;

  // Row one is the windowed three and ONLY those three. issuesOpen is a lifetime
  // figure — 197 is the whole backlog, while only 30 issues were opened in the last
  // month — so putting it under a "last 30 days" heading presented a lifetime count
  // as a monthly one. It moves to row two under its own `// today` scope, where the
  // release and the snapshot date already live. Closed and open stay adjacent in
  // reading order across the row break, which is what the pairing needs; what it
  // cannot survive is sharing one wrong label.
  const windowed: { key: string; body: React.ReactNode }[] = [
    { key: "commits", body: <>{n(a.commits)} commits</> },
    { key: "pulls", body: <>{n(a.pullsMerged)} PRs merged</> },
    { key: "closed", body: <>{n(a.issuesClosed)} issues closed</> },
  ];

  return (
    <section className="border-y border-hair" aria-label="Repository activity">
      {/* Each row carries its own `//` scope kicker. One row would not fit at 1280px
          anyway, but the reason for the split is that the two rows mean different
          things — a single kicker over all of it is what made the lifetime open-issue
          count read as a 30-day one. */}
      <div className="wrap flex flex-col items-center gap-[0.3rem] py-[0.85rem] font-mono text-[0.76rem] text-ink-mute">
        <ul
          className="flex flex-wrap items-center justify-center gap-x-[1.15rem] gap-y-[0.3rem]"
          role="list"
        >
          <li className="whitespace-nowrap text-accent">
            {`// last ${a.windowDays} days on ${a.branch}`}
          </li>
          {windowed.map((f) => (
            <li key={f.key} className="whitespace-nowrap">
              {f.body}
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center justify-center gap-x-[1.15rem] gap-y-[0.3rem]">
          <span className="whitespace-nowrap text-accent">{"// today"}</span>
          <span className="whitespace-nowrap">{n(a.issuesOpen)} issues open</span>
          {a.latestRelease ? (
            <span className="whitespace-nowrap">
              latest{" "}
              <a
                className="text-ink [text-underline-offset:2px] hover:text-accent hover:underline"
                href={a.latestRelease.url}
                target="_blank"
                rel="noreferrer"
              >
                {a.latestRelease.tag}
              </a>
            </span>
          ) : null}
          <span className="whitespace-nowrap">snapshot {isoDay(a.generatedAt)}</span>
          <a
            className="inline-flex items-center gap-[0.4rem] whitespace-nowrap text-ink-soft transition-colors hover:text-accent"
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
          >
            <GitHubGlyph width={13} height={13} />
            browse the repo <span aria-hidden="true">→</span>
          </a>
        </div>
      </div>
    </section>
  );
}
