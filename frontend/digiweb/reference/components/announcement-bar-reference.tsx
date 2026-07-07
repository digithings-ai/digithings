"use client";

import { useState } from "react";

/** Graphite's announcement bar: 48px above the nav, the ENTIRE bar is the
 *  link, dismissible, an a11y region. Content-gated in production — it only
 *  ships with real news (a release, a launch), never evergreen marketing. */
export function AnnouncementBarReference() {
  const [dismissed, setDismissed] = useState(false);

  return (
    <section className="section-block" id="announcement-bar">
      <p className="kicker">{"// announcement bar"}</p>
      <h2 className="title">Only with real news.</h2>
      <p className="section-copy">
        48px above the nav, the entire bar is one click target, and it can be dismissed for
        good. Content-gated: it exists when there is a release to announce and not otherwise —
        never evergreen marketing.
      </p>

      {dismissed ? (
        <p className="annc-restore">
          <button type="button" className="btn-quiet" onClick={() => setDismissed(false)}>
            Restore the demo bar
          </button>
        </p>
      ) : (
        <div className="annc-bar" role="region" aria-label="Announcement">
          <a href="#announcement-bar" className="annc-link" onClick={(e) => e.preventDefault()}>
            <span>digiquant v2.4 ships kelly-capped position sizing.</span>
            <b>Read the changelog →</b>
          </a>
          <button
            type="button"
            className="annc-close"
            aria-label="Dismiss announcement"
            onClick={() => setDismissed(true)}
          >
            ✕
          </button>
        </div>
      )}
    </section>
  );
}
