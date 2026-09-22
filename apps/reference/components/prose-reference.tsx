/**
 * Prose grammar — the shared long-form page atoms (D1, #4429): the PageHead
 * opener (mono kicker + display title + lede), the hairline RuledList/RuledRow
 * definition grammar, and inline Mono. Promoted from digithings-web's app-local
 * `_company/prose.tsx`; utilities only, so the grammar travels with the kit.
 * Static display template.
 */
import { Mono, PageHead, RuledList, RuledRow } from "@digithings/ui";

const ROWS: { term: string; body: string }[] = [
  { term: "digibase", body: "The shared library every other module sits on." },
  { term: "digigraph", body: "Supervisor + sub-graph orchestration over the module graph." },
  { term: "digikey", body: "Identity: RS256 JWTs and scoped API keys, checked per route." },
];

export function ProseReference() {
  return (
    <section className="section-block prose-grammar">
      <p className="kicker">{"// prose grammar"}</p>
      <h2 className="title">The long-form page grammar.</h2>
      <p className="section-copy">
        The atoms the company and legal pages assemble from — a kicker, a display title with an
        accent <Mono>em</Mono>, a lede (PageHead), hairline definition rows (RuledList/RuledRow),
        and inline mono (Mono). Every one is token-backed utilities, so the shape lives in the kit
        rather than one site.
      </p>

      <PageHead kicker={"// specimen"} title={<>Infrastructure, <em>not a product.</em></>}>
        The opener mirrors the landing hero at subpage scale: a mono kicker, a display title with
        an accent italic, and one lede paragraph.
      </PageHead>

      <RuledList>
        {ROWS.map((r) => (
          <RuledRow key={r.term} term={r.term}>
            {r.body}
          </RuledRow>
        ))}
      </RuledList>
    </section>
  );
}
