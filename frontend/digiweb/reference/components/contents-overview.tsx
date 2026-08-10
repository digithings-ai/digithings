/**
 * Contents overview — the home-page index of every design family, each a card
 * linking to its page with a one-line blurb. The map that mirrors the top nav.
 * Static display template.
 */
import Link from "next/link";

const FAMILIES = [
  { href: "/", label: "Foundations", blurb: "Livery system, feature picker, button & CTA states." },
  { href: "/controls", label: "Controls", blurb: "Custom dropdown pane, search, nav buttons, form fields." },
  { href: "/layout-patterns", label: "Layout", blurb: "Feature cell, bento grid, scaled product frames." },
  { href: "/typography", label: "Typography", blurb: "Scroll-linked word reveals and the copy & voice grammar." },
  { href: "/data", label: "Data", blurb: "Dot matrix, count-up stats, card deck, pricing, matrix." },
  { href: "/finance", label: "Finance", blurb: "Lightweight-Charts dashboards, order book, money metrics." },
  { href: "/tearsheet", label: "Tearsheet", blurb: "Print-grade SVG tearsheet: synced charts, matrix, trade log, cards." },
  { href: "/effects", label: "Effects", blurb: "Cursor-follow graph, terminals, pipeline, ambient mesh." },
  { href: "/chrome", label: "Chrome", blurb: "Announcement bar, scroll-aware nav, tabs, colophon footer." },
  { href: "/terminal", label: "Terminal", blurb: "Diegetic CLI session and streaming chat transcript." },
  { href: "/chatbot", label: "Chatbot", blurb: "Thinking chain, composer, markdown, inline chart & graph, widgets." },
  { href: "/symbols", label: "Symbols", blurb: "Module emblems, wordmarks, QR, vendor logos, glyphs." },
  { href: "/account", label: "Account", blurb: "Login, sign-up, payment, settings, profile templates." },
] as const;

export function ContentsOverview() {
  return (
    <section className="section-block contents-overview">
      <p className="kicker">{"// contents"}</p>
      <h2 className="title">Thirteen families, one system.</h2>
      <p className="section-copy">
        Every page is one family of design elements, all sharing the same tokens, livery, and
        motion laws. Start anywhere — the top bar carries the same map.
      </p>

      <div className="mt-[1.2rem] grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-[0.7rem]">
        {FAMILIES.map((f, i) => (
          <Link key={f.href + f.label} href={f.href} className="co-card">
            <span className="font-mono text-[0.6rem] tracking-[0.1em] text-accent">{String(i).padStart(2, "0")}</span>
            <span className="font-mono text-[0.95rem] text-ink">{f.label}</span>
            <span className="text-[0.8rem] leading-[1.4] text-ink-soft">{f.blurb}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
