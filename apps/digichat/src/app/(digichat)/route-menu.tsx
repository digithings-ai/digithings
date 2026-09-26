/**
 * Root menu (single-route plan, menu-root fork).
 *
 * Bare `/` renders no chat — just this menu linking the three modes.
 * Plain server links, zero client JS.
 */
export function RouteMenu() {
  const cards = [
    {
      href: "/?mode=product",
      title: "Product chat",
      desc: "The hosted product thread.",
    },
    {
      href: "/?mode=embed",
      title: "Embed preview",
      desc: "The tenant iframe surface.",
    },
    {
      href: "/?mode=catalog",
      title: "Skin catalog",
      desc: "Browse every skin, side by side.",
    },
  ];
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-8 bg-background px-4 text-foreground">
      <div className="flex flex-col items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">digichat</h1>
        <p className="text-sm text-muted-foreground">Pick a surface.</p>
      </div>
      <nav
        aria-label="digichat surfaces"
        className="grid w-full max-w-2xl gap-3 sm:grid-cols-3"
      >
        {cards.map((card) => (
          <a
            key={card.href}
            href={card.href}
            className="flex flex-col gap-1 rounded-lg border border-border bg-card p-5 transition-colors hover:bg-muted"
          >
            <span className="text-sm font-medium">{card.title}</span>
            <span className="text-xs text-muted-foreground">{card.desc}</span>
          </a>
        ))}
      </nav>
    </main>
  );
}
