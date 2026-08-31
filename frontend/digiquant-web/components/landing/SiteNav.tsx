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
 * The in-nav "Desk" text link still scrolls to the `/#desk` explainer section —
 * text link explains, button launches. Path `/olympus/` stays until ADR-0026 wave 2.
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
          {/* Desktop twin of the sheet CTA below — same destination + label,
              plain wordmark-style link rather than a solid `.btn-primary`
              pill (same call as digithings.ai's DtNav "ask digichat", #1450
              round 3+): a filled button read as a bright, standoffish box
              next to the quiet GitHub glyph and the plain inline links either
              side of it. `.dq-nav-olympus-cta` (globals.css) is just icon +
              label in the theme's own ink tone, no button chrome — kept
              apart from `.olympus-cta`, which stays for the hover-animation
              hooks on the mark's strokes, not the button dress. Hides at the
              same 880px breakpoint where the inline links yield to the
              hamburger, so narrow viewports keep the sheet button as the
              only dashboard entry. hidden! (important): `.olympus-cta`'s
              `display: inline-flex` is unlayered on purpose in globals.css
              (sheet-slot rule) and outranks the layered utility. */}
          <a
            className="dq-nav-olympus-cta olympus-cta max-[880px]:hidden!"
            href="/olympus/"
            aria-label="Open the digiquant dashboard"
          >
            <DigiquantMark size={16} />
            <span>digiquant</span>
          </a>
        </>
      }
      cta={
        <a className="btn btn-primary olympus-cta" href="/olympus/" aria-label="Open the digiquant dashboard">
          <DigiquantMark size={18} />
          <span>digiquant</span>
        </a>
      }
    />
  );
}
