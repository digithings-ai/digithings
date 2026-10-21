"use client";

/**
 * Header treatments for the variant exploration (2026-09-21).
 *
 * `NavShell` expresses a lot through props, so two of these are just prop
 * configurations. `MonoNav` is a bar `NavShell` has no shape for today — it is
 * composed here **locally and deliberately throwaway**: if the flat mono-link
 * bar is picked, it is promoted into `NavShell` (or a new `chrome.tsx` part)
 * with tests rather than copied into `app/page.tsx`.
 */
import { usePathname } from "next/navigation";
import Link from "next/link";

import {
  CopyCommand,
  CtaLink,
  GitHubGlyph,
  IconLink,
  isNavGroup,
  NavShell,
  ThemeToggle,
  type NavItem,
  type NavLink,
} from "@digithings/ui";
import { Brand, DT_NAV_PRIMARY } from "@/app/_nav";
import { DigiChatMark } from "@digithings/digichat-ui";
import { INSTALL } from "./content";

/** Drops NavGroup entries — a group has no place in a bar with no dropdowns. */
function flatLinks(links: NavItem[]): NavLink[] {
  return links.filter((l) => !isNavGroup(l)) as NavLink[];
}

/** The shipped bar, for comparison against the others. */
export function StandardNav() {
  return (
    <NavShell
      brand={<Brand />}
      links={DT_NAV_PRIMARY}
      skipTo="#main"
      homeLabel="digithings home"
      actions={
        <>
          <IconLink href="https://github.com/digithings-ai" label="digithings on GitHub" external>
            <GitHubGlyph />
          </IconLink>
          <CtaLink href="/chat" variant="outline" className="max-[880px]:hidden!" aria-label="Ask digichat" icon={<DigiChatMark size={16} />}>
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

/** The quietest bar: three links, theme toggle, nothing else. */
export function QuietNav() {
  const pathname = usePathname();
  return (
    <NavShell
      brand={<Brand />}
      links={flatLinks(DT_NAV_PRIMARY).slice(0, 4)}
      currentPath={pathname ?? undefined}
      skipTo="#main"
      homeLabel="digithings home"
    />
  );
}

/** A bar that yields: it appears only while the cursor is in the top strip. */
export function FloatNav() {
  const pathname = usePathname();
  return (
    <NavShell
      brand={<Brand />}
      links={DT_NAV_PRIMARY}
      currentPath={pathname ?? undefined}
      skipTo="#main"
      homeLabel="digithings home"
      autoHide="hover"
      cta={
        <CtaLink href="/chat" aria-label="Ask digichat" icon={<DigiChatMark size={18} />}>
          Ask digichat
        </CtaLink>
      }
    />
  );
}

/**
 * An app-local flat bar — brand, inline mono links, a theme toggle, one
 * hairline. No dropdowns, no buttons, no logo cluster. Throwaway: see the file
 * header.
 */
export function MonoNav() {
  const pathname = usePathname();
  const linkClass = (href: string) =>
    `font-mono text-[0.8rem] no-underline hover:text-ink ${pathname === href ? "text-ink" : "text-ink-soft"}`;
  return (
    <header className="sticky top-0 z-40 w-full border-b border-hair bg-bg">
      <div className="flex h-[var(--nav-shell-h)] items-center gap-[1.6rem] px-[var(--page-pad)]">
        <Link href="/" aria-label="digithings home" className="flex items-center text-ink no-underline">
          <Brand />
        </Link>
        <nav aria-label="Main" className="hidden items-center gap-[1.3rem] max-[880px]:hidden min-[880px]:flex">
          {flatLinks(DT_NAV_PRIMARY).map((l) =>
            l.external ? (
              <a
                key={l.href}
                href={l.href}
                target="_blank"
                rel="noopener noreferrer"
                className={linkClass(l.href)}
              >
                {l.label}
              </a>
            ) : (
              <Link
                key={l.href}
                href={l.href}
                aria-current={pathname === l.href ? "page" : undefined}
                className={linkClass(l.href)}
              >
                {l.label}
              </Link>
            ),
          )}
        </nav>
        <div className="ml-auto flex items-center gap-[0.8rem]">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

/**
 * A slim install strip that sits above the bar and *is* the copy affordance:
 * the first thing on the page is the command that starts the stack. Composed
 * from the real `CopyCommand`, so the copied string and the shown string are
 * the same string by construction.
 */
export function CommandStrip() {
  return (
    <div className="w-full border-b border-hair bg-surface">
      <div className="flex flex-wrap items-center gap-x-[1rem] gap-y-[0.6rem] px-[var(--page-pad)] py-[0.6rem]">
        <span className="font-mono text-[0.68rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
          install
        </span>
        <div className="min-w-[18rem] flex-1">
          <CopyCommand samples={INSTALL} ariaLabel="Install command" />
        </div>
      </div>
    </div>
  );
}
