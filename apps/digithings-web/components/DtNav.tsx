"use client";
/**
 * DtNav — digithings.ai's composition of the shared <NavShell/> primitive
 * (@digithings/ui). Supersedes the app-local DigiNav copy: the scroll grammar
 * (settle after 8px, yield past 180px, return on scroll-up), the hamburger
 * portal sheet, body scroll lock, Escape/scrim dismissal and focus return are
 * owned by NavShell; everything digithings-specific arrives here as props — the
 * brand mark, the wayfinding links, the skip-link target, the GitHub icon in
 * the tail, and the "Ask digichat" CTA (sheet, plus a compact tail link on wide
 * viewports). The CTA treatments are the kit's CtaLink/IconLink, so the button
 * dress lives once in buttonVariants — no `.dc-nav-cta` stays here.
 */
import { usePathname } from "next/navigation";
import { NavShell, GitHubGlyph, IconLink, CtaLink } from "@digithings/ui";
import { Brand, DT_NAV_PRIMARY } from "@/app/_nav";
import { DigiChatMark } from "@digithings/digichat-ui";

export function DtNav({ autoHide }: { autoHide?: "scroll" | "hover" }) {
  const pathname = usePathname();
  return (
    <NavShell
      brand={<Brand />}
      links={DT_NAV_PRIMARY}
      currentPath={pathname ?? undefined}
      skipTo="#main"
      homeLabel="digithings home"
      autoHide={autoHide}
      actions={
        <>
          <IconLink
            href="https://github.com/digithings-ai"
            label="digithings on GitHub"
            external
          >
            <GitHubGlyph />
          </IconLink>
          {/* Desktop twin of the sheet CTA below — the quiet `outline` dress
              (the same buttonVariants vocabulary as every other CTA) rather
              than a filled pill, so it recedes next to the GitHub glyph.
              Hides at the same 880px breakpoint where the inline links yield to
              the hamburger, so narrow viewports keep the sheet button as the
              only digichat entry. */}
          <CtaLink
            href="/chat"
            variant="outline"
            className="max-[880px]:hidden!"
            aria-label="Ask digichat"
            icon={<DigiChatMark size={16} />}
          >
            ask digichat
          </CtaLink>
        </>
      }
      cta={
        <CtaLink href="/chat" aria-label="Ask digichat" icon={<DigiChatMark size={18} />}>
          Ask digichat
        </CtaLink>
      }
    />
  );
}
