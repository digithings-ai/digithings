"use client";

import { useState, type MouseEvent } from "react";
import { AnnouncementBar } from "@digithings/web";

/** Graphite's announcement bar: 48px above the nav, the ENTIRE bar is the
 *  link, dismissible, an a11y region. Content-gated in production — it only
 *  ships with real news (a release, a launch), never evergreen marketing.
 *  Consumes the shared <AnnouncementBar/> primitive from @digithings/web. */
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
        <p className="mt-[1.2rem]">
          <button type="button" className="btn-quiet" onClick={() => setDismissed(false)}>
            Restore the demo bar
          </button>
        </p>
      ) : (
        <AnnouncementBar
          href="#announcement-bar"
          cta="Read the changelog →"
          onDismiss={() => setDismissed(true)}
          onLinkClick={(e: MouseEvent<HTMLAnchorElement>) => e.preventDefault()}
          className="mt-[1.2rem]"
        >
          digiquant v2.4 ships kelly-capped position sizing.
        </AnnouncementBar>
      )}
    </section>
  );
}
