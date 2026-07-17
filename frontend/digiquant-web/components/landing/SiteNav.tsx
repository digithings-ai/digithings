"use client";
/**
 * digiquant.io top bar — the shared NavShell primitive (@digithings/web)
 * dressed with this app's brand, links, GitHub tail action, and the Olympus
 * CTA — in the sheet on narrow viewports, and as a compact tail button right
 * of the GitHub glyph on wide ones (#1450 round 3). Supersedes the app-local
 * DqNav copy (#1401): the scroll grammar
 * (settle after 8px, yield past 180px), hamburger, portal sheet, Escape/scrim
 * dismissal, and body-scroll lock all live in the primitive; only the dress
 * arrives from here.
 *
 * The Olympus CTA opens the dashboard app at `/olympus/` (a full cross-app
 * navigation — Olympus is a separate export assembled into `dist/olympus/`, so
 * it's a plain <a>, not a Next <Link>, and matches the subsystems page's
 * "Open Olympus" button). The in-nav "Olympus" text link still scrolls to the
 * `/#olympus` explainer section — text link explains, button launches.
 */
import { NavShell, GitHubGlyph } from "@digithings/web";
import { Brand, DQ_NAV_PRIMARY } from "@/app/_nav";
import { OlympusMark } from "./OlympusMark";

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
              compact .btn-sm dress; hides at the same 880px breakpoint where
              the inline links yield to the hamburger, so narrow viewports keep
              the sheet button as the only Olympus entry. hidden! (important):
              .olympus-cta's `display: inline-flex` is unlayered on purpose in
              globals.css (sheet-slot rule) and outranks the layered utility. */}
          <a
            className="btn btn-primary btn-sm olympus-cta max-[880px]:hidden!"
            href="/olympus/"
            aria-label="Open the Olympus dashboard"
          >
            <OlympusMark size={16} />
            <span>Olympus</span>
          </a>
        </>
      }
      cta={
        <a className="btn btn-primary olympus-cta" href="/olympus/" aria-label="Open the Olympus dashboard">
          <OlympusMark size={18} />
          <span>Olympus</span>
        </a>
      }
    />
  );
}
