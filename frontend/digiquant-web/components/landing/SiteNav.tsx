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
 * The dashboard CTA opens the app at `/olympus/` (a full cross-app
 * navigation — the dashboard is a separate export assembled into `dist/olympus/`, so
 * it's a plain <a>, not a Next <Link>, and matches the subsystems page).
 * Desktop chrome is the teal dashboard mark only (aria-label names the
 * destination). The sheet CTA still says Open dashboard. "Desk" in the text
 * links scrolls to `/#desk`. Path `/olympus/` stays until ADR-0026 wave 2.
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
          {/* Desktop twin of the sheet CTA — icon-only teal mark. The wordmark
              is already digiquant; a "dashboard" label next to the mark was a
              second name in the chrome. `.dq-nav-olympus-cta` (globals.css)
              sizes the hit target; `.olympus-cta` owns the stroke-draw idle
              (every 10s) and the hover replay. Hides at the same 880px
              breakpoint where the inline links yield to the hamburger.
              hidden! (important): `.olympus-cta`'s `display: inline-flex` is
              unlayered on purpose in globals.css (sheet-slot rule) and
              outranks the layered utility. */}
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
