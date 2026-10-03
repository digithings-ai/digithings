"use client";
/**
 * digiquant.io top bar — NavShell + showcase wayfinding (#4895).
 * Loud CTA tours the desk display. The operator dashboard is not this site.
 */
import { NavShell, GitHubGlyph, CtaLink, IconLink } from "@digithings/ui";
import { Brand, DQ_NAV_PRIMARY } from "@/app/_nav";

export function SiteNav() {
  return (
    <NavShell
      brand={<Brand />}
      links={DQ_NAV_PRIMARY}
      homeLabel="digiquant home"
      skipTo="#main"
      actions={
        <>
          <IconLink
            href="https://github.com/digithings-ai"
            label="digiquant on GitHub"
            external
          >
            <GitHubGlyph />
          </IconLink>
          <CtaLink href="/#desk" variant="ghost" size="sm" className="max-[880px]:hidden!">
            Tour
          </CtaLink>
        </>
      }
      cta={
        <CtaLink href="/#desk" variant="default" size="default">
          Tour the desk
        </CtaLink>
      }
    />
  );
}
