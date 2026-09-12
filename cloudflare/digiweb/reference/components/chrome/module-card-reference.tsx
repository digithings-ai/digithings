import { ModuleCard, moduleById, type ModuleNode } from "@digithings/web";

/**
 * Module card — the landing-page module tile from @digithings/web, the sibling
 * of Nav/Footer/Colophon in the shared chrome file. One card per module: the
 * module emblem in its own accent, a tier badge, the name and role, and a
 * compact stack row. Neither marketing home renders a module grid today (both
 * compose their own index rows), so this is the tile for any surface that
 * wants one — emblem, tier badge, name, role, stack. The accent hairline
 * fills on hover and the card lifts — the one motion moment, CSS-driven. Both marketing sites build their module
 * grid from this component; the three specimens below span every tier so the
 * .dg-tier variants (core → accent, support → ink-mute, roadmap → warn) all
 * show. Fed straight from the shared module registry.
 */
const TIER_SPECIMENS: ModuleNode[] = ["digigraph", "digismith", "digistore"]
  .map((id) => moduleById(id))
  .filter((m): m is ModuleNode => Boolean(m));

export function ModuleCardReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// module card"}</p>
      <h2 className="title">One tile per module.</h2>
      <p className="section-copy">
        <code>ModuleCard</code> from <code>@digithings/web</code> is the landing-page module tile —
        emblem, tier badge, name, role, and a compact stack row, wired to the shared module
        registry. Neither marketing home renders a module grid today; the tile stands ready for
        any surface that wants one. The accent hairline fills on hover and the card lifts; one
        card per tier below (core, support, roadmap) so the badge variants all read.
      </p>

      <div className="mt-[1.4rem] grid gap-[1rem] sm:grid-cols-2 lg:grid-cols-3">
        {TIER_SPECIMENS.map((m) => (
          <ModuleCard key={m.id} m={m} />
        ))}
      </div>
    </section>
  );
}
