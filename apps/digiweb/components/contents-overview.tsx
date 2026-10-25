"use client";

/**
 * Contents overview — the home-page index of every design family, each a card
 * linking to its page with a one-line blurb. It reads the same `lib/nav.ts`
 * data the top bar does, so the map and the bar can never disagree.
 *
 * The card is the stock `Card` from `@digithings/ui/ui`. The current-page
 * signal stays: the link carries `aria-current`, the Card picks it up through
 * the group-aria variant as an accent ring. Reference-only (`lab`) surfaces
 * render in a separate, de-emphasised row.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Card, CardContent } from "@digithings/ui/ui";
import { LAB_NAV, PRIMARY_NAV, type NavItem } from "@/lib/nav";

function FamilyCard({ item, index }: { item: NavItem; index: number }) {
  const pathname = usePathname();
  // Boundary-checked, not a bare startsWith: /data would otherwise also
  // read "current" on a hypothetical /data-v2 route (or any other sibling
  // sharing the prefix) — match only the exact path or a path continuing
  // after a "/".
  const isActive =
    item.href === "/"
      ? pathname === "/"
      : pathname === item.href || pathname.startsWith(`${item.href}/`);

  return (
    <Link
      href={item.href}
      aria-current={isActive ? "page" : undefined}
      className="group block"
    >
      <Card className="h-full group-aria-[current=page]:ring-accent">
        <CardContent className="flex flex-col gap-[0.25rem]">
          <span className="font-mono text-[0.6rem] tracking-[0.1em] text-accent">
            {String(index).padStart(2, "0")}
          </span>
          <span className="font-mono text-[0.95rem] text-ink">{item.label}</span>
          <span className="text-[0.8rem] leading-[1.4] text-ink-soft">{item.blurb}</span>
        </CardContent>
      </Card>
    </Link>
  );
}

export function ContentsOverview() {
  return (
    <section className="section-block contents-overview" id="contents">
      <p className="kicker">{"// contents"}</p>
      <h2 className="title">{PRIMARY_NAV.length} families, one system.</h2>
      <p className="section-copy">
        Every page is one family of design elements, all sharing the same tokens, livery, and
        motion laws. The top bar carries the same map; <code>/rtl</code> proves the whole canon
        mirrors, and the reference-only surfaces below stay out of the shipped set.
      </p>

      <div className="mt-[1.2rem] grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-[0.7rem]">
        {PRIMARY_NAV.map((item, i) => (
          <FamilyCard key={item.href} item={item} index={i} />
        ))}
      </div>

      <p className="mb-0 mt-[1.6rem] font-mono text-[0.58rem] uppercase tracking-[0.14em] text-ink-mute">
        reference-only
      </p>
      <div className="mt-[0.6rem] grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-[0.7rem]">
        {LAB_NAV.map((item, i) => (
          <FamilyCard key={item.href} item={item} index={i} />
        ))}
      </div>
    </section>
  );
}
