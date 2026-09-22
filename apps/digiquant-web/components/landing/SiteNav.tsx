"use client";
/**
 * digiquant.io top bar — the shared NavShell primitive (@digithings/ui)
 * dressed with this app's brand, links, current path, GitHub tail action, and
 * the dashboard CTA — in the sheet on narrow viewports, and as a compact
 * mark-only link right of the GitHub glyph on wide ones (#1450 round 3).
 * Supersedes the app-local DqNav copy (#1401): the scroll grammar (settle after
 * 8px, yield past 180px), hamburger, portal sheet, Escape/scrim dismissal,
 * body-scroll lock and focus return all live in the primitive; only the dress
 * arrives from here. The GitHub and sheet CTAs are the kit's IconLink/CtaLink,
 * so the button dress lives once in buttonVariants; the desktop dashboard mark
 * keeps its bespoke ol-pulse/ol-draw animation (the `.dq-mark`/`.dq-stroke`
 * hook), triggered through the mark's own wrapper.
 *
 * Dashboard CTA is a plain <a href="/dashboard/"> (separate export).
 */
import { usePathname } from "next/navigation";
import { NavShell, GitHubGlyph, DigiquantMark, IconLink, CtaLink } from "@digithings/ui";
import { Brand, DQ_NAV_PRIMARY } from "@/app/_nav";

export function SiteNav() {
  const pathname = usePathname();
  return (
    <NavShell
      brand={<Brand />}
      links={DQ_NAV_PRIMARY}
      currentPath={pathname ?? undefined}
      skipTo="#main"
      homeLabel="digiquant home"
      actions={
        <>
          <IconLink
            href="https://github.com/digithings-ai"
            label="digiquant on GitHub"
            external
          >
            <GitHubGlyph />
          </IconLink>
          {/* Icon-only desktop twin of the sheet CTA, with the dashboard mark
              animation. hidden! beats the unlayered .dq-nav-mark-cta display. */}
          <a
            className="dq-nav-mark-cta max-[880px]:hidden!"
            href="/dashboard/"
            aria-label="Open the dashboard"
          >
            <DigiquantMark size={20} />
          </a>
        </>
      }
      cta={
        <CtaLink
          href="/dashboard/"
          aria-label="Open the dashboard"
          icon={<DigiquantMark size={18} />}
        >
          <span>Open dashboard</span>
        </CtaLink>
      }
    />
  );
}
