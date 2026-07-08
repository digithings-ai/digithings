/**
 * DtNav — digithings.ai's composition of the shared <NavShell/> primitive
 * (@digithings/web). Supersedes the app-local DigiNav copy: the scroll grammar
 * (settle after 8px, yield past 180px, return on scroll-up), the hamburger
 * portal sheet, body scroll lock and Escape/scrim dismissal are owned by
 * NavShell; everything digithings-specific arrives here as props — the QR
 * brand mark, the wayfinding links, the GitHub icon in the tail, and the
 * "Ask digichat" CTA in the narrow-viewport sheet.
 */
import Link from "next/link";
import { NavShell } from "@digithings/web";
import { Brand, DT_NAV_PRIMARY } from "@/app/_nav";
import { DigiChatMark } from "@/components/DigiChatMark";

function GitHubGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
      <path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17 4.7 18 5 18 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z" />
    </svg>
  );
}

export function DtNav() {
  return (
    <NavShell
      brand={<Brand />}
      links={DT_NAV_PRIMARY}
      homeLabel="digithings home"
      actions={
        <a
          className="btn-icon"
          href="https://github.com/digithings-ai"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="digithings on GitHub"
        >
          <GitHubGlyph />
        </a>
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
