"use client";
/**
 * digiquant.io top bar — the shared NavShell primitive (@digithings/web)
 * dressed with this app's brand, links, GitHub tail action, and the Olympus
 * sheet CTA. Supersedes the app-local DqNav copy (#1401): the scroll grammar
 * (settle after 8px, yield past 180px), hamburger, portal sheet, Escape/scrim
 * dismissal, and body-scroll lock all live in the primitive; only the dress
 * arrives from here.
 */
import Link from "next/link";
import { NavShell, GitHubGlyph } from "@digithings/web";
import { Brand, DQ_NAV_PRIMARY } from "@/app/_nav";
import { OlympusMark } from "./OlympusMark";

/** NavShell wires close-on-navigate into its own links, but the cta slot is
 *  opaque to it. A hash navigation (→ /#olympus) never remounts the page, so
 *  the sheet would stay open over the scrolled content — synthesize the
 *  Escape the open menu already listens for. */
function closeSheet() {
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
}

export function SiteNav() {
  return (
    <NavShell
      brand={<Brand />}
      links={DQ_NAV_PRIMARY}
      homeLabel="digiquant home"
      actions={
        <a
          className="btn btn-ghost btn-sm btn-icon"
          href="https://github.com/digithings-ai"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="digiquant on GitHub"
        >
          <GitHubGlyph />
        </a>
      }
      cta={
        <Link className="btn btn-primary olympus-cta" href="/#olympus" onClick={closeSheet}>
          <OlympusMark size={18} />
          <span>Olympus</span>
        </Link>
      }
    />
  );
}
