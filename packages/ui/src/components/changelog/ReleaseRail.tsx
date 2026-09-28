/**
 * The release rail — the changelog's row grammar, OpenCode-informed: a two-column
 * grid per release with the version, date and product pinned in a sticky aside,
 * and the shipped title with its highlights in the wide column under a hairline.
 * Static, so the whole changelog renders without JavaScript (D1, #4429). Generic:
 * rows arrive as data and the caller owns the order, so a site can fold its own
 * release source in without this part knowing where releases come from.
 */
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

export interface ReleaseRailItem {
  /** The product or package the release belongs to, e.g. `digichat`. */
  product: string;
  /** The version as published, e.g. `v2.3.1`. */
  version: string;
  /** The release date, ISO `YYYY-MM-DD`. */
  date: string;
  /** The published title. */
  title: string;
  /** The release URL, so the version stays the link. */
  href: string;
  /** The release kind as tagged upstream, e.g. `fix` or `release`. */
  tag?: string;
  /** Optional highlights, one plain clause each. */
  entries?: ReactNode[];
}

export interface ReleaseRailProps {
  items: ReleaseRailItem[];
  className?: string;
}

export function ReleaseRail({ items, className }: ReleaseRailProps) {
  return (
    <ol className={cn("m-0 grid list-none gap-0 p-0", className)}>
      {items.map((item) => (
        <li
          key={`${item.product}-${item.version}`}
          className="grid gap-[0.9rem] border-t border-hair py-[1.6rem] first:border-t-0 first:pt-0 last:pb-0 sm:grid-cols-[180px_1fr] sm:gap-[3rem]"
        >
          <div className="flex flex-col gap-[0.3rem] sm:sticky sm:top-[5rem] sm:self-start">
            <a
              href={item.href}
              className="font-mono text-[0.9rem] font-medium text-ink underline-offset-[3px] hover:underline"
            >
              {item.version}
            </a>
            <span className="font-mono text-[var(--type-meta)] tracking-[0.02em] text-ink-mute">
              <time dateTime={item.date}>{item.date}</time>
              {item.tag ? ` · ${item.tag}` : ""}
            </span>
            <span className="font-mono text-[var(--type-meta)] tracking-[0.02em] text-ink-mute">
              {item.product}
            </span>
          </div>
          <div className="min-w-0">
            <p className="m-0 text-[length:var(--type-body)] font-medium leading-[1.5] text-ink">
              {item.title}
            </p>
            {item.entries && item.entries.length > 0 ? (
              <ul className="m-0 mt-[0.8rem] grid list-none gap-[0.6rem] p-0">
                {item.entries.map((entry, index) => (
                  <li
                    key={index}
                    className="flex gap-[0.75rem] text-[0.9rem] leading-[1.7] text-ink-soft"
                  >
                    <span aria-hidden="true" className="shrink-0 font-mono text-ink-mute">
                      [*]
                    </span>
                    <span>{entry}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
