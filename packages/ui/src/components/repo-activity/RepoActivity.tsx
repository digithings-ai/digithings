"use client";

/**
 * RepoActivity — snapshot-first public GitHub velocity, compact or detailed.
 * Renders the committed snapshot on the server; an optional live refresh runs
 * after hydration and replaces every figure atomically, or is ignored so the
 * snapshot never blanks. Stars/forks/watchers are not collected. 30-day
 * velocity and the current backlog are labeled as different measurements.
 *
 * The detailed contribution grid shortens as its column narrows rather than
 * scrolling horizontally (`weeks`, below).
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/ui/styles/repo-activity.css";
 *                 @source "<path-to>/packages/ui/src/components/repo-activity";
 */
import { useEffect, useRef, useState, type RefObject } from "react";

import { CardRail } from "../data-layout";
import { GitHubGlyph } from "../icons";
import { fetchRepoActivityLive } from "./fetch";
import { RepoHeatmap } from "./RepoHeatmap";
import {
  cloneParts,
  grouped,
  isoDay,
  type RepoActivityLiveConfig,
  type RepoActivitySnapshot,
  type RepoIssueItem,
  type RepoPullItem,
} from "./types";

/**
 * One module's current version, for the activity variant's release rail.
 * `name` is the module (digichat, digigraph, …); `version` is the tag as it
 * should be read, without the module prefix repeated.
 *
 * `title` and `date` are the optional live layer. A host that has fetched the
 * module's newest GitHub release fills them with that release's call-out line
 * and publish date, and points `url` at the tag. A module with no release of
 * its own leaves them out rather than inventing a feature line — the declared
 * `version` is the fallback for exactly those modules, because release-please
 * only cuts releases for digichat and digiskills, so most of the rail is the
 * version each module declares for itself
 * (see apps/digithings-web/lib/moduleCounts.ts).
 */
export type RepoModuleRelease = {
  name: string;
  version: string;
  url?: string;
  /** The newest release's call-out line, when a release exists. */
  title?: string;
  /** ISO publish stamp of that release (`2026-09-21T12:38:12Z`). */
  date?: string;
};

/** The maintainer behind the repo, credited under the activity variant. */
export type RepoContributor = {
  name: string;
  role?: string;
  /** Avatar URL; a monogram is drawn when it is absent. */
  avatarUrl?: string;
  url?: string;
};

export type RepoActivityProps = {
  variant: "compact" | "detailed" | "activity";
  snapshot: RepoActivitySnapshot;
  repoUrl: string;
  /** When set, fetch public GitHub data after mount; keep snapshot on any failure. */
  live?: RepoActivityLiveConfig;
  cloneCommand?: string;
  contributingUrl?: string;
  /**
   * Weeks of contribution history to request, for the detailed variant. The
   * grid never exceeds this, but it is measured down when the column is too
   * narrow for it (see `weeksThatFit`), so the history shortens instead of
   * scrolling. Defaults to 53 — a full year, GitHub-style.
   */
  weeks?: number;
  /** Activity variant: the current version of every module, newest first. */
  moduleReleases?: RepoModuleRelease[];
  /** Activity variant: the maintainer credited under the ledger. */
  contributor?: RepoContributor;
  className?: string;
};

export function RepoActivity({
  variant,
  snapshot,
  repoUrl,
  live,
  cloneCommand,
  contributingUrl,
  weeks = 53,
  moduleReleases,
  contributor,
  className,
}: RepoActivityProps) {
  const [data, setData] = useState(snapshot);
  const [source, setSource] = useState<"snapshot" | "live">("snapshot");
  const heatRef = useRef<HTMLDivElement | null>(null);
  /** Measured fit; null until a browser measures, so SSR keeps `weeks`. */
  const [fitWeeks, setFitWeeks] = useState<number | null>(null);

  useEffect(() => {
    if (!live) return;
    let cancelled = false;
    fetchRepoActivityLive(live).then(
      (next) => {
        if (cancelled) return;
        setData(applyLive(snapshot, next));
        setSource("live");
      },
      () => {
        /* keep snapshot — no loading or error surface */
      },
    );
    return () => {
      cancelled = true;
    };
    // Mount-only: the static snapshot is the SSR contract; live is a one-shot enhance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Shorten the grid to the column instead of letting it scroll. Guarded on
  // ResizeObserver so the server and jsdom keep rendering exactly `weeks`, which
  // is what every existing snapshot assertion expects.
  //
  // The width is read from the element, and the element can measure 0 on the
  // first pass (before the parent grid has laid out, or on a route where the
  // band is still below the fold). Feeding that 0 to `weeksThatFit` would floor
  // the result at MIN_HEAT_WEEKS and then the effect's own `[weeks]` dep would
  // keep re-clamping to the shortened value, so the graph stayed at 12 weeks
  // even after the column reached full width. Two guards: skip a zero-width
  // measurement so the default (`weeks`) holds, and re-measure once on the next
  // frame, because a ResizeObserver only fires on a size *change* and will not
  // report a width that was already correct by the time it attached.
  useEffect(() => {
    const el = heatRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      const width = el.clientWidth;
      if (width <= 0) return;
      setFitWeeks(weeksThatFit(width, weeks));
    };
    measure();
    const frame = requestAnimationFrame(measure);
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [weeks]);

  const heatWeeks = fitWeeks ?? weeks;
  // RepoHeatmap labels the window from `weeks` but totals EVERY cell it is
  // handed, so the series has to be cut to the same window or the heading would
  // count weeks the grid does not draw.
  const heatData = data.dailyContributions
    ? data.dailyContributions.slice(-heatWeeks * 7)
    : undefined;

  const cls = [
    "ra",
    variant === "compact" ? "ra-compact" : variant === "activity" ? "ra-activity" : "ra-detailed",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article
      className={cls}
      data-variant={variant}
      data-source={source}
      aria-label="Repository activity"
    >
      {variant === "compact" ? (
        <Compact data={data} repoUrl={repoUrl} source={source} />
      ) : variant === "activity" ? (
        <Activity
          data={data}
          repoUrl={repoUrl}
          heatRef={heatRef}
          heatWeeks={heatWeeks}
          heatData={heatData}
          moduleReleases={moduleReleases}
          contributor={contributor}
        />
      ) : (
        <Detailed
          data={data}
          repoUrl={repoUrl}
          source={source}
          cloneCommand={cloneCommand}
          contributingUrl={contributingUrl}
          heatRef={heatRef}
          heatWeeks={heatWeeks}
          heatData={heatData}
        />
      )}
    </article>
  );
}

/**
 * The detailed grid is a fixed 10px cell with a 3px gap, sitting after a 1.65rem
 * day rail and a 0.45rem gap (`repo-activity.css`), so a W-week frame measures
 * `33.6 + 13W` px. Past the container it would scroll horizontally
 * (`.ra-heat-body { overflow-x: auto }`), which reads as a cut-off history; the
 * owner asked for the history to shorten instead. So the width picks the week
 * count — 53 at a desktop frame (~720px of grid), fewer as the column narrows,
 * and never below a quarter so the graph stays readable.
 */
const HEAT_CELL = 10;
const HEAT_CELL_GAP = 3;
const HEAT_RAIL = 26.4 + 7.2;
const MIN_HEAT_WEEKS = 12;

function weeksThatFit(columnWidth: number, ceiling: number): number {
  // An unmeasured column is not a narrow one: shorten nothing until a real
  // width exists. The caller already skips zero-width reads, so this is the
  // belt to that braces.
  if (!Number.isFinite(columnWidth) || columnWidth <= 0) return ceiling;
  const columns = Math.floor(
    (columnWidth - HEAT_RAIL + HEAT_CELL_GAP) / (HEAT_CELL + HEAT_CELL_GAP),
  );
  // The grid draws calendar weeks, so a W-week span can occupy W+1 columns when
  // the range starts or ends mid-week. Reserve that column — without it the
  // frame overruns the body by one cell and the body scrolls after all, which
  // is the behaviour this exists to remove.
  const weeks = columns - 1;
  return Math.max(Math.min(MIN_HEAT_WEEKS, ceiling), Math.min(ceiling, weeks));
}

function applyLive(
  snapshot: RepoActivitySnapshot,
  live: Omit<RepoActivitySnapshot, "features" | "modules">,
): RepoActivitySnapshot {
  return {
    ...snapshot,
    ...live,
    features: snapshot.features,
    modules: snapshot.modules,
  };
}

function Compact({
  data,
  repoUrl,
  source,
}: {
  data: RepoActivitySnapshot;
  repoUrl: string;
  source: "snapshot" | "live";
}) {
  const pulls = (data.mergedPulls ?? []).slice(0, 3);
  return (
    <>
      <header className="ra-head">
        <p className="ra-kicker">{`// last ${data.windowDays} days on ${data.branch}`}</p>
        <Stamp source={source} at={data.generatedAt} />
      </header>
      <ul className="ra-metrics" role="list">
        <Metric n={data.commits} label="commits" />
        <Metric n={data.pullsMerged} label="PRs merged" />
        <Metric n={data.issuesClosed} label="issues closed" />
      </ul>
      <div className="ra-meta">
        <ReleaseLink release={data.latestRelease} />
        <RepoLink href={repoUrl} />
      </div>
      {pulls.length ? (
        <ol className="ra-list" role="list">
          {pulls.map((p) => (
            <PullRow key={p.number} item={p} stamp={p.mergedAt} />
          ))}
        </ol>
      ) : null}
    </>
  );
}

/**
 * The in-between variant: summary metrics beside the contribution grid, then a
 * horizontal rail of every module's current version and the maintainer.
 *
 * The detailed variant answers "what is happening" with two ledgers (merged
 * recently, open issues); the compact one answers "is this alive" with three
 * counts. This one answers "is this alive, and what has shipped" — the metrics
 * and the graph are kept, the ledgers are dropped for the version ledger, and
 * the graph is asked to fit (`fit`) so it fills its column instead of scrolling
 * and its squares scale with the width.
 *
 * The grid sits in the right column because it is the widest element and the
 * metrics are narrow: putting the counts left and the graph right is what keeps
 * the first rows from being mostly empty, and the graph then expands into
 * whatever width is left. Below 900px it stacks.
 *
 * No latest-release line and no snapshot stamp here — the owner called that
 * "ai slop like the latest digichat v1.5 snapshot date ... isn't necessary" and
 * the version rail already carries every module's release. The repo link moves
 * to the foot's bottom-right corner, where "browse the repo" belongs.
 */
function Activity({
  data,
  repoUrl,
  heatRef,
  heatWeeks,
  heatData,
  moduleReleases,
  contributor,
}: {
  data: RepoActivitySnapshot;
  repoUrl: string;
  heatRef: RefObject<HTMLDivElement | null>;
  heatWeeks: number;
  heatData: RepoActivitySnapshot["dailyContributions"];
  moduleReleases?: RepoModuleRelease[];
  contributor?: RepoContributor;
}) {
  const releases = moduleReleases ?? [];
  return (
    <>
      <div className="ra-activity-top">
        <div className="ra-activity-metrics">
          <div className="ra-group">
            <p className="ra-kicker">{`// last ${data.windowDays} days on ${data.branch}`}</p>
            <ul className="ra-metrics" role="list">
              <Metric n={data.commits} label="commits" />
              <Metric n={data.pullsMerged} label="PRs merged" />
              <Metric n={data.issuesClosed} label="issues closed" />
            </ul>
          </div>
          <div className="ra-group">
            <p className="ra-kicker">{"// current backlog"}</p>
            <ul className="ra-metrics" role="list">
              <Metric n={data.pullsOpen} label="PRs open" />
              <Metric n={data.issuesOpen} label="issues open" />
            </ul>
          </div>
        </div>
        <div className="ra-group ra-activity-heat" ref={heatRef}>
          <p className="ra-kicker">{`// contributions — ${
            heatWeeks >= 50 ? "last year" : `last ${heatWeeks} weeks`
          }`}</p>
          <RepoHeatmap pulls={data.mergedPulls} data={heatData} weeks={heatWeeks} fit />
        </div>
      </div>

      {releases.length || contributor ? (
        <div className="ra-activity-foot">
          {releases.length ? (
            <div className="ra-versions">
              <p className="ra-kicker">{"// current versions"}</p>
              {/* The ledger is the kit's own horizontal rail — the same element
                  the strategy library uses, promoted from the design reference's
                  changelog rail. The owner asked for the releases "in a
                  horizontal scrollable pane like you'll find in the data page".
                  The rail knows nothing about its children, so each release is a
                  card carrying its own name, version and optional live line. */}
              <CardRail ariaLabel="Current version of every module">
                {releases.map((r) => (
                  <ReleaseCard key={r.name} release={r} />
                ))}
              </CardRail>
            </div>
          ) : null}
          {contributor ? (
            <div className="ra-contributor">
              <p className="ra-kicker">{"// maintainer"}</p>
              <div className="ra-contributor-body">
                <ContributorAvatar contributor={contributor} />
                <div>
                  {contributor.url ? (
                    <a href={contributor.url} target="_blank" rel="noreferrer">
                      {contributor.name}
                    </a>
                  ) : (
                    <span>{contributor.name}</span>
                  )}
                  {contributor.role ? (
                    <span className="ra-contributor-role">{contributor.role}</span>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}
          <div className="ra-meta">
            <RepoLink href={repoUrl} />
          </div>
        </div>
      ) : null}
    </>
  );
}

/**
 * One release card in the version rail. `role="listitem"` because the rail's
 * track is the `role="list"`; the sizing and snap-align live in
 * `repo-activity.css` (`.ra-release-card`), since the call site here is the kit
 * itself rather than an app. A module whose version is only declared — no
 * GitHub release — shows its name and version and stops there: no feature line
 * and no date, because there is no release to read them from.
 */
function ReleaseCard({ release }: { release: RepoModuleRelease }) {
  return (
    <article className="ra-release-card" role="listitem">
      <div className="ra-release-head">
        <span className="ra-release-name">{release.name}</span>
        {release.date ? (
          <time className="ra-release-date" dateTime={release.date}>
            {isoDay(release.date)}
          </time>
        ) : null}
      </div>
      {release.url ? (
        <a className="ra-release-version" href={release.url} target="_blank" rel="noreferrer">
          {release.version}
        </a>
      ) : (
        <span className="ra-release-version">{release.version}</span>
      )}
      {release.title ? <p className="ra-release-title">{release.title}</p> : null}
    </article>
  );
}

function ContributorAvatar({ contributor }: { contributor: RepoContributor }) {
  if (contributor.avatarUrl) {
    return (
      // Plain <img>: the kit ships no next/image dependency and the avatar is a
      // single fixed-size square.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        className="ra-avatar"
        src={contributor.avatarUrl}
        alt=""
        width={36}
        height={36}
        loading="lazy"
      />
    );
  }
  const initial = contributor.name.trim().charAt(0).toUpperCase();
  return (
    <span className="ra-avatar ra-avatar--mono" aria-hidden="true">
      {initial}
    </span>
  );
}

function Detailed({
  data,
  repoUrl,
  source,
  cloneCommand,
  contributingUrl,
  heatRef,
  heatWeeks,
  heatData,
}: {
  data: RepoActivitySnapshot;
  repoUrl: string;
  source: "snapshot" | "live";
  cloneCommand?: string;
  contributingUrl?: string;
  heatRef: RefObject<HTMLDivElement | null>;
  heatWeeks: number;
  heatData: RepoActivitySnapshot["dailyContributions"];
}) {
  const pulls = (data.mergedPulls ?? []).slice(0, 6);
  const issues = (data.openIssues ?? []).slice(0, 6);
  const [cloneHead, cloneTail] = cloneCommand ? cloneParts(cloneCommand) : ["", ""];

  return (
    <>
      <div className="ra-group">
        <p className="ra-kicker">{`// last ${data.windowDays} days on ${data.branch}`}</p>
        <ul className="ra-metrics" role="list">
          <Metric n={data.commits} label="commits" />
          <Metric n={data.pullsMerged} label="PRs merged" />
          <Metric n={data.issuesClosed} label="issues closed" />
        </ul>
      </div>
      <div className="ra-group">
        <p className="ra-kicker">{"// current backlog"}</p>
        <ul className="ra-metrics" role="list">
          <Metric n={data.pullsOpen} label="PRs open" />
          <Metric n={data.issuesOpen} label="issues open" />
        </ul>
      </div>
      <div className="ra-group" ref={heatRef}>
        <p className="ra-kicker">{`// contributions — ${
          heatWeeks >= 50 ? "last year" : `last ${heatWeeks} weeks`
        }`}</p>
        <RepoHeatmap pulls={data.mergedPulls} data={heatData} weeks={heatWeeks} />
      </div>
      <div className="ra-meta">
        <ReleaseLink release={data.latestRelease} />
        <Stamp source={source} at={data.generatedAt} />
        <RepoLink href={repoUrl} />
      </div>
      {cloneCommand || contributingUrl ? (
        <div className="ra-actions">
          {cloneCommand ? (
            <div className="ra-clone">
              <code>
                {cloneHead}
                <wbr />
                {cloneTail}
              </code>
              <CopyButton text={cloneCommand} />
            </div>
          ) : null}
          {contributingUrl ? (
            <div className="ra-cta">
              <a href={contributingUrl} target="_blank" rel="noreferrer">
                Contributing guide <span aria-hidden="true">→</span>
              </a>
              <a href={`${repoUrl}/issues`} target="_blank" rel="noreferrer">
                <GitHubGlyph width={14} height={14} />
                Open issues
              </a>
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="ra-cols">
        <div>
          <p className="ra-kicker">{"// merged recently"}</p>
          {pulls.length ? (
            <ol className="ra-list" role="list">
              {pulls.map((p) => (
                <PullRow key={p.number} item={p} stamp={p.mergedAt} />
              ))}
            </ol>
          ) : null}
        </div>
        <div>
          <p className="ra-kicker">{"// open issues"}</p>
          {issues.length ? (
            <ol className="ra-list" role="list">
              {issues.map((issue) => (
                <IssueRow key={issue.number} item={issue} />
              ))}
            </ol>
          ) : null}
        </div>
      </div>
    </>
  );
}

function Metric({ n, label }: { n: number; label: string }) {
  return (
    <li className="ra-metric">
      <span className="ra-n">{grouped(n)}</span>
      <span className="ra-l">{label}</span>
    </li>
  );
}

function Stamp({ source, at }: { source: "snapshot" | "live"; at: string }) {
  return (
    <p className="ra-stamp">
      {source} {isoDay(at)}
    </p>
  );
}

function ReleaseLink({ release }: { release: RepoActivitySnapshot["latestRelease"] }) {
  if (!release) return null;
  return (
    <p className="ra-release">
      latest{" "}
      <a href={release.url} target="_blank" rel="noreferrer">
        {release.tag}
      </a>
    </p>
  );
}

function RepoLink({ href }: { href: string }) {
  return (
    <a className="ra-repo" href={href} target="_blank" rel="noreferrer">
      <GitHubGlyph width={13} height={13} />
      browse the repo <span aria-hidden="true">→</span>
    </a>
  );
}

function PullRow({ item, stamp }: { item: RepoPullItem; stamp: string | null }) {
  return (
    <li className="ra-row">
      <a className="ra-num" href={item.url} target="_blank" rel="noreferrer">
        #{item.number}
      </a>
      <span className="ra-title">{item.title}</span>
      <span className="ra-date">{isoDay(stamp)}</span>
    </li>
  );
}

function IssueRow({ item }: { item: RepoIssueItem }) {
  return (
    <li className="ra-row">
      <a className="ra-num" href={item.url} target="_blank" rel="noreferrer">
        #{item.number}
      </a>
      <span className="ra-title">{item.title}</span>
      <span className="ra-date">{isoDay(item.updatedAt)}</span>
    </li>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="ra-copy"
      aria-label="Copy the clone command"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(
          () => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          },
          () => {},
        );
      }}
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}
