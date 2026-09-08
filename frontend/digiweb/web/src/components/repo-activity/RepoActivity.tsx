"use client";

/**
 * RepoActivity — snapshot-first public GitHub velocity, compact or detailed.
 * Renders the committed snapshot on the server; an optional live refresh runs
 * after hydration and replaces every figure atomically, or is ignored so the
 * snapshot never blanks. Stars/forks/watchers are not collected. 30-day
 * velocity and the current backlog are labeled as different measurements.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/repo-activity.css";
 *                 @source "<path-to>/digiweb/web/src/components/repo-activity";
 */
import { useEffect, useState } from "react";

import { GitHubGlyph } from "../icons";
import { fetchRepoActivityLive } from "./fetch";
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
  className?: string;
};

export function RepoActivity({
  variant,
  snapshot,
  repoUrl,
  live,
  cloneCommand,
  contributingUrl,
  className,
}: RepoActivityProps) {
  const [data, setData] = useState(snapshot);
  const [source, setSource] = useState<"snapshot" | "live">("snapshot");

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
        />
      )}
    </article>
  );
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
}: {
  data: RepoActivitySnapshot;
  repoUrl: string;
  source: "snapshot" | "live";
  cloneCommand?: string;
  contributingUrl?: string;
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
