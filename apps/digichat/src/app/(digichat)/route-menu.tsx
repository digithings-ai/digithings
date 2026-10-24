/**
 * Root menu (single-route plan, menu-root fork).
 *
 * Bare `/` renders no chat — just this menu linking the three modes.
 * Command-palette-style pick list on the house grid: hairline rows, no radius,
 * no card, no shadow, no second typeface. Plain server links, zero client JS.
 * Frames: `.app-menu*` in `src/styles/app-shell-states.css`.
 */
import { p } from "@/lib/base-path";

export function RouteMenu() {
  // These are plain <a> links, not Next's <Link>, so they carry no basePath:
  // prefix them by hand or the menu jumps to the apex site when the app is
  // served under /chat (DIG-5121).
  const root = p("/").replace(/\/+$/, "") || "/";
  const rows = [
    {
      href: `${root}?mode=product`,
      key: "1",
      title: "Product chat",
      desc: "The hosted product thread.",
    },
    {
      href: `${root}?mode=embed`,
      key: "2",
      title: "Embed preview",
      desc: "The tenant iframe surface.",
    },
    {
      href: `${root}?mode=catalog`,
      key: "3",
      title: "Skin catalog",
      desc: "Browse every skin, side by side.",
    },
  ];
  return (
    <main className="app-menu">
      <div className="app-menu-inner">
        <header className="app-menu-head">
          <h1 className="app-menu-title">digichat</h1>
          <p className="app-menu-copy">One skin, three surfaces.</p>
        </header>
        <nav aria-label="digichat surfaces" className="app-menu-list">
          {rows.map((row) => (
            <a key={row.href} href={row.href} className="app-menu-row">
              <span className="app-menu-key" aria-hidden="true">
                {row.key}
              </span>
              <span className="app-menu-text">
                <span className="app-menu-row-title">{row.title}</span>
                <span className="app-menu-desc">{row.desc}</span>
              </span>
              <span className="app-menu-go" aria-hidden="true">
                ▸
              </span>
            </a>
          ))}
        </nav>
        <p className="app-menu-note">Same thread on every surface.</p>
      </div>
    </main>
  );
}
