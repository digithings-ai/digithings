import Link from "next/link";

const FAMILIES = [
  { href: "/", label: "Foundations", blurb: "Livery system, feature picker, button & CTA states." },
  { href: "/layout-patterns", label: "Layout", blurb: "Feature cell, bento grid, scaled product frames." },
  { href: "/typography", label: "Typography", blurb: "Scroll-linked word reveals and the copy & voice grammar." },
  { href: "/data", label: "Data", blurb: "Dot matrix, count-up stats, card deck, pricing, matrix." },
  { href: "/finance", label: "Finance", blurb: "Lightweight-Charts tearsheet, order book, money metrics." },
  { href: "/effects", label: "Effects", blurb: "Cursor-follow graph, terminals, pipeline, ambient mesh." },
  { href: "/chrome", label: "Chrome", blurb: "Announcement bar, scroll-aware nav, colophon footer." },
  { href: "/terminal", label: "Terminal", blurb: "Diegetic CLI session and streaming chat transcript." },
  { href: "/symbols", label: "Symbols", blurb: "Module emblems, wordmarks, QR, vendor logos, glyphs." },
  { href: "/account", label: "Account", blurb: "Login, sign-up, payment, settings, profile templates." },
] as const;

export function ContentsOverview() {
  return (
    <section className="section-block contents-overview">
      <p className="kicker">{"// contents"}</p>
      <h2 className="title">Ten families, one system.</h2>
      <p className="section-copy">
        Every page is one family of design elements, all sharing the same tokens, livery, and
        motion laws. Start anywhere — the top bar carries the same map.
      </p>

      <div className="co-grid">
        {FAMILIES.map((f, i) => (
          <Link key={f.href + f.label} href={f.href} className="co-card">
            <span className="co-index">{String(i).padStart(2, "0")}</span>
            <span className="co-label">{f.label}</span>
            <span className="co-blurb">{f.blurb}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
