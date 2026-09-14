"use client";

import { useState, type MouseEventHandler, type ReactNode } from "react";

/**
 * AnnouncementBar — Graphite's announcement bar promoted from the design
 * reference (chrome/announcement-bar): a 48px strip above the nav where the
 * ENTIRE bar is one click target, plus a ✕ that dismisses it. An a11y region.
 * Content-gated by doctrine: it ships with real news (a release, a launch),
 * never evergreen marketing — the component takes the news line and CTA via
 * props and carries no copy of its own.
 *
 * Dismissal: internal state by default; pass `dismissed` to control it, and
 * persist however the app likes in `onDismiss` (localStorage, a cookie …) —
 * persistence is deliberately consumer-owned.
 *
 * The frame (.annc-bar) sits in @layer components so call-site utilities can
 * retune it (production strips the demo radius with rounded-none, etc.);
 * .annc-link keeps its class for the parent-hover-descendant CTA underline.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/effects-chrome.css";
 *                 @source "<path-to>/digiweb/web/src/components/effects-chrome";
 */
export type AnnouncementBarProps = {
  /** Destination — the entire bar is the link. */
  href: string;
  /** The news line — "digiquant v2.4 ships kelly-capped position sizing." */
  children: ReactNode;
  /** Accented bold call-to-action — "Read the changelog →". */
  cta?: ReactNode;
  /** Controlled dismissal; omit to let the bar own its state. */
  dismissed?: boolean;
  /** Uncontrolled initial state — e.g. hydrated from storage. */
  defaultDismissed?: boolean;
  /** Fired when the ✕ is pressed (persist it here). */
  onDismiss?: () => void;
  /** Render the ✕ at all. */
  dismissible?: boolean;
  /** Anchor click passthrough (SPA routing, analytics, demo preventDefault). */
  onLinkClick?: MouseEventHandler<HTMLAnchorElement>;
  ariaLabel?: string;
  className?: string;
};

export function AnnouncementBar({
  href,
  children,
  cta,
  dismissed,
  defaultDismissed = false,
  onDismiss,
  dismissible = true,
  onLinkClick,
  ariaLabel = "Announcement",
  className,
}: AnnouncementBarProps) {
  const [selfDismissed, setSelfDismissed] = useState(defaultDismissed);
  if (dismissed ?? selfDismissed) return null;

  return (
    <div
      className={`annc-bar${className ? ` ${className}` : ""}`}
      role="region"
      aria-label={ariaLabel}
    >
      <a href={href} className="annc-link" onClick={onLinkClick}>
        <span>{children}</span>
        {cta ? <b>{cta}</b> : null}
      </a>
      {dismissible ? (
        <button
          type="button"
          className="mr-[0.3rem] h-10 w-10 flex-shrink-0 cursor-pointer border-0 bg-transparent text-[0.8rem] text-ink-mute hover:text-ink"
          aria-label="Dismiss announcement"
          onClick={() => {
            setSelfDismissed(true);
            onDismiss?.();
          }}
        >
          ✕
        </button>
      ) : null}
    </div>
  );
}
