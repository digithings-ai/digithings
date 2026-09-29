/**
 * Root menu (single-route plan, menu-root fork).
 *
 * Bare `/` renders no chat — just this menu linking the three modes.
 * Command-palette-style pick list, DigiWeb-aligned kit tokens.
 * Plain server links, zero client JS.
 */
export function RouteMenu() {
  const rows = [
    {
      href: "/?mode=product",
      key: "1",
      title: "Product chat",
      desc: "The hosted product thread.",
    },
    {
      href: "/?mode=embed",
      key: "2",
      title: "Embed preview",
      desc: "The tenant iframe surface.",
    },
    {
      href: "/?mode=catalog",
      key: "3",
      title: "Skin catalog",
      desc: "Browse every skin, side by side.",
    },
  ];
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-background px-4 text-foreground">
      <div className="w-full max-w-md">
        <div className="mb-5 flex flex-col items-center gap-1.5">
          <h1 className="text-xl font-semibold tracking-tight">digichat</h1>
          <p className="text-sm text-muted-foreground">
            One skin, three surfaces.
          </p>
        </div>
        <nav
          aria-label="digichat surfaces"
          className="overflow-hidden rounded-xl border border-border bg-card shadow-sm"
        >
          {rows.map((row, i) => (
            <a
              key={row.href}
              href={row.href}
              className={
                "group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none" +
                (i > 0 ? " border-t border-border" : "")
              }
            >
              <kbd
                aria-hidden="true"
                className="flex size-6 shrink-0 items-center justify-center rounded-md border border-border bg-background font-mono text-[11px] text-muted-foreground"
              >
                {row.key}
              </kbd>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="text-sm font-medium">{row.title}</span>
                <span className="truncate text-xs text-muted-foreground">
                  {row.desc}
                </span>
              </span>
              <span
                aria-hidden="true"
                className="shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
              >
                →
              </span>
            </a>
          ))}
        </nav>
        <p className="mt-4 text-center text-xs text-muted-foreground">
          Same thread on every surface.
        </p>
      </div>
    </main>
  );
}
