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
import { NavShell, GitHubGlyph } from "@digithings/web";
import { Brand, DT_NAV_PRIMARY } from "@/app/_nav";
import { DigiChatMark } from "@/components/DigiChatMark";

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
