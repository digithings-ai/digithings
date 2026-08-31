"use client";
/**
 * digiquant.io top bar — the shared NavShell primitive (@digithings/web)
 * dressed with this app's brand, links, GitHub tail action, and the dashboard
 * CTA — in the sheet on narrow viewports, and as a compact tail button right
 * of the GitHub glyph on wide ones (#1450 round 3). Supersedes the app-local
 * DqNav copy (#1401): the scroll grammar
 * (settle after 8px, yield past 180px), hamburger, portal sheet, Escape/scrim
 * dismissal, and body-scroll lock all live in the primitive; only the dress
 * arrives from here.
 *
 * Dashboard CTA is a plain <a href="/olympus/"> (separate export; path stays
 * until ADR-0026 wave 2). Desktop: teal mark only. Sheet: Open dashboard.
 */
import { NavShell, GitHubGlyph } from "@digithings/web";
import { Brand, DQ_NAV_PRIMARY } from "@/app/_nav";
import { DigiquantMark } from "./OlympusMark";

export function SiteNav() {
  return (
    <NavShell
      brand={<Brand />}
      links={DQ_NAV_PRIMARY}
      homeLabel="digiquant home"
      actions={
        <>
          <a
            className="btn btn-ghost btn-sm btn-icon"
            href="https://github.com/digithings-ai"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="digiquant on GitHub"
          >
            <GitHubGlyph />
          </a>
          {/* Icon-only desktop twin. hidden! beats unlayered .olympus-cta display. */}
          <a
            className="dq-nav-olympus-cta olympus-cta max-[880px]:hidden!"
            href="/olympus/"
            aria-label="Open the dashboard"
          >
            <DigiquantMark size={20} />
          </a>
        </>
      }
      cta={
        <a className="btn btn-primary olympus-cta" href="/olympus/" aria-label="Open the dashboard">
          <DigiquantMark size={18} />
          <span>Open dashboard</span>
        </a>
      }
    />
  );
}
