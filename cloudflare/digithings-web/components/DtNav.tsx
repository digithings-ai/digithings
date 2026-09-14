/**
 * DtNav — digithings.ai's composition of the shared <NavShell/> primitive
 * (@digithings/web). Supersedes the app-local DigiNav copy: the scroll grammar
 * (settle after 8px, yield past 180px, return on scroll-up), the hamburger
 * portal sheet, body scroll lock and Escape/scrim dismissal are owned by
 * NavShell; everything digithings-specific arrives here as props — the QR
 * brand mark, the wayfinding links, the GitHub icon in the tail, and the
 * "Ask digichat" CTA — in the narrow-viewport sheet, and as a compact tail
 * button right of the GitHub glyph on wide viewports (#1450 round 3).
 */
import Link from "next/link";
import { NavShell, GitHubGlyph } from "@digithings/web";
import { Brand, DT_NAV_PRIMARY } from "@/app/_nav";
import { DigiChatMark } from "@digithings/digichat-ui";

export function DtNav({ autoHide }: { autoHide?: "scroll" | "hover" }) {
  return (
    <>
      {/* Skip-to-content (full-UI-suite critique, digithings-web target, P2):
          every page mounts DtNav first, so it is the one place that reaches
          every page's persistent nav ahead of #main. Visually hidden until
          keyboard focus (translate off-screen, restored on :focus-visible) --
          same pattern as the design reference's own .skip-link. Plain Tailwind
          utilities rather than a new CSS class: the frontend canon guard's
          family census (#1421) would reject an app-local class here. */}
      <a
        href="#main"
        className="fixed top-2 left-2 z-30 -translate-y-[200%] rounded-none bg-[var(--accent)] px-[0.9rem] py-2 font-mono text-[0.72rem] text-[var(--on-accent)] no-underline focus-visible:translate-y-0"
      >
        Skip to content
      </a>
      <NavShell
        brand={<Brand />}
        links={DT_NAV_PRIMARY}
        homeLabel="digithings home"
        autoHide={autoHide}
        actions={
          <>
            <a
              className="btn-icon"
              href="https://github.com/digithings-ai"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="digithings on GitHub"
            >
              <GitHubGlyph />
            </a>
            {/* Desktop twin of the sheet CTA below — same destination, plain
                wordmark-style link rather than a solid `.btn-primary` pill: next
                to the quiet GitHub glyph and inline links, a filled button read
                as a bright, standoffish box. `.dc-nav-cta` (globals.css) is
                just icon + label in the theme's own ink tone, no button chrome.
                Hides at the same 880px breakpoint where the inline links yield
                to the hamburger, so narrow viewports keep the sheet button as
                the only digichat entry. */}
            <Link
              className="dc-nav-cta max-[880px]:hidden"
              href="/chat"
              aria-label="Ask digichat"
            >
              <DigiChatMark size={16} />
              ask digichat
            </Link>
          </>
        }
        cta={
          <Link className="btn btn-primary" href="/chat" aria-label="Ask digichat">
            <DigiChatMark size={18} />
            Ask digichat
          </Link>
        }
      />
    </>
  );
}
