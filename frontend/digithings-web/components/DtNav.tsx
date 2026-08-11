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
              as a bright, standoffish box. `.dt-nav-chat-cta` (globals.css) is
              just icon + label in the theme's own ink tone, no button chrome.
              Hides at the same 880px breakpoint where the inline links yield
              to the hamburger, so narrow viewports keep the sheet button as
              the only digichat entry. */}
          <Link
            className="dt-nav-chat-cta max-[880px]:hidden"
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
  );
}
