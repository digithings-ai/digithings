"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const PAGES = [
  { href: "/", label: "Foundations" },
  { href: "/typography", label: "Typography" },
  { href: "/data", label: "Data" },
  { href: "/chrome", label: "Chrome" },
  { href: "/terminal", label: "Terminal" },
  { href: "/account", label: "Account" },
] as const;

/** Shared top bar for the design-reference app. Each page holds one family
 *  of design elements; the bar is the only chrome shared across them. */
export function SiteNav() {
  const pathname = usePathname();

  return (
    <nav className="site-nav" aria-label="Design reference sections">
      <Link href="/" className="site-nav-mark">
        design<em>ref</em>
      </Link>
      <ul>
        {PAGES.map((page) => {
          const active =
            page.href === "/" ? pathname === "/" : pathname.startsWith(page.href);
          return (
            <li key={page.href}>
              <Link href={page.href} aria-current={active ? "page" : undefined}>
                {page.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
