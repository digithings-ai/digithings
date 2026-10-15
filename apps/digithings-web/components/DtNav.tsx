"use client";
/**
 * DtNav — digithings.ai's composition of the shared <NavShell/> primitive
 * (@digithings/ui). Supersedes the app-local DigiNav copy: the scroll grammar
 * (settle after 8px, yield past 180px, return on scroll-up), the hamburger
 * portal sheet, body scroll lock, Escape/scrim dismissal and focus return are
 * owned by NavShell; everything digithings-specific arrives here as props — the
 * brand mark, the wayfinding links, the skip-link target, the GitHub icon in
 * the tail, and the digichat hero banner (sheet, plus the wide-bar tail). The
 * banner is the chat entry: it builds on load and stays live.
 *
 * The bar is pinned: it settles after 8px but never yields on scroll-down
 * (owner: the top bar should stay fixed to the top). Pass
 * `autoHide="hover"` explicitly for the non-scrolling chat shells.
 */
import { usePathname } from "next/navigation";
import { NavShell, GitHubGlyph, IconLink } from "@digithings/ui";
import { DIGICHAT } from "@digithings/hero-banner/definitions";
import { Brand, DT_NAV_PRIMARY } from "@/app/_nav";
import { ScrollBanner } from "@/components/landing/ScrollBanner";

const NAV_HREFS = DT_NAV_PRIMARY.flatMap((item) =>
  "items" in item ? item.items.map((i) => i.href) : [item.href],
).filter((href) => href.startsWith("/"));

/** digichat hero banner. It replaces the old ask button in the bar and the sheet. */
function DigichatNavMark({ className }: { className?: string }) {
  return (
    <a href="/chat" aria-label="digichat" className={className}>
      <ScrollBanner def={DIGICHAT} inView={false} replayLoading className="w-[7.2rem]" />
    </a>
  );
}

/** The nav entry whose section holds `pathname`: the longest nav href that is
 *  the path or one of its parents, so /docs/api/digiquant/ lights "API" and
 *  not "Docs". NavShell itself marks exact routes only. */
function navSection(pathname: string | null): string | undefined {
  if (!pathname) return undefined;
  const path = pathname.replace(/\/+$/, "") || "/";
  let best: string | undefined;
  for (const href of NAV_HREFS) {
    const within = href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
    if (within && (best === undefined || href.length > best.length)) best = href;
  }
  return best ?? pathname;
}

export function DtNav({ autoHide = "pinned" }: { autoHide?: "scroll" | "hover" | "pinned" }) {
  const pathname = usePathname();
  return (
    <NavShell
      brand={<Brand />}
      links={DT_NAV_PRIMARY}
      currentPath={navSection(pathname)}
      skipTo="#main"
      homeLabel="digithings home"
      autoHide={autoHide}
      clipToFrame
      actions={
        <>
          <IconLink
            href="https://github.com/digithings-ai"
            label="digithings on GitHub"
            external
          >
            <GitHubGlyph />
          </IconLink>
          <DigichatNavMark className="inline-flex items-center max-[880px]:hidden!" />
        </>
      }
      cta={<DigichatNavMark className="inline-flex items-center" />}
    />
  );
}
