/**
 * Bento grid — an asymmetric module bento: the supervisor anchors a 2×2 hero, the
 * flagship takes a wide cell, the rest fall into units, each wearing its module
 * livery. Static layout template.
 */
import { Emblem, moduleById } from "@digithings/web";

type Cell = { id: string; span: "hero" | "wide" | "tall" | "unit"; blurb: string };

// An asymmetric bento: the supervisor anchors a 2x2 hero, the flagship takes a
// wide cell, the rest fall into units. Each cell wears its module livery.
const CELLS: Cell[] = [
  { id: "digigraph", span: "hero", blurb: "The supervisor. Routes every request to the module that owns it." },
  { id: "digiquant", span: "wide", blurb: "NautilusTrader quant — research that ends in an order." },
  { id: "digisearch", span: "unit", blurb: "Retrieval-augmented answers." },
  { id: "digichat", span: "unit", blurb: "The terminal, inhabited." },
  { id: "digikey", span: "tall", blurb: "JWT + scoped API keys. Auth on by default." },
  { id: "digivault", span: "unit", blurb: "Obsidian-style markdown vault." },
  { id: "digismith", span: "unit", blurb: "Tracing across the graph." },
];

export function BentoGridReference() {
  return (
    <section className="section-block bento">
      <p className="kicker">{"// bento grid"}</p>
      <h2 className="title">The stack, at a glance.</h2>
      <p className="section-copy">
        An asymmetric grid where card weight signals hierarchy — the supervisor anchors a large
        cell, the flagship runs wide, supporting modules fall into units. Each tile wears its
        module livery via an accent scope; hover lifts the hairline. Collapses to one column on
        mobile.
      </p>

      <div className="bento-grid">
        {CELLS.map((cell) => {
          const mod = moduleById(cell.id);
          if (!mod) return null;
          return (
            <article key={cell.id} className={`bento-cell bento-${cell.span} accent-${cell.id}`}>
              <div className="bento-cell-top">
                <Emblem id={cell.id} size={cell.span === "hero" ? 40 : 26} />
                <span className="bento-tier">{mod.tier}</span>
              </div>
              <div className="bento-cell-body">
                <h3 className="bento-name">{mod.name}</h3>
                <p className="bento-role">{cell.blurb}</p>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
