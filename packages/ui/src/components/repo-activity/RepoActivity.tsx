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

export type RepoActivityProps = {
  variant: "compact" | "detailed";
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
  useEffect(() => {
    const el = heatRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = () => setFitWeeks(weeksThatFit(el.clientWidth, weeks));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [weeks]);

  const heatWeeks = fitWeeks ?? weeks;
  // RepoHeatmap labels the window from `weeks` but totals EVERY cell it is
  // handed, so the series has to be cut to the same window or the heading would
  // count weeks the grid does not draw.
  const heatData = data.dailyContributions
    ? data.dailyContributions.slice(-heatWeeks * 7)
    : undefined;

  const cls = ["ra", variant === "compact" ? "ra-compact" : "ra-detailed", className ?? ""]
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
