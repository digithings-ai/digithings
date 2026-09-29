/**
 * Document grammar — the framed-column marketing page: one bordered column with a
 * hairline between sections, a small document-scale type ladder, prose measure, and
 * the `[*]` + `<strong>Label</strong>` row. This is the opencode-informed language the
 * public sites are rebuilt on (D1, #4429): no eyebrow kickers, no display hero, no
 * alternating bands. Static display template.
 */
import {
  DocumentFrame,
  GlyphList,
  GlyphRow,
  PageTitle,
  Prose,
  Section,
} from "@digithings/ui";

const PROPERTIES: { label: string; clause: string }[] = [
  { label: "MIT, and public", clause: "No open-core teaser with the useful half held back." },
  { label: "Self-hostable anywhere", clause: "One compose file, your hosts, your domain." },
  { label: "Bring your own tokens", clause: "The stack persists no provider credentials." },
  { label: "A glass box, not a black box", clause: "A correlation id and an audit line per hop." },
];

export function DocumentReference() {
  return (
    <section className="section-block" id="document">
      <p className="kicker">{"// document grammar"}</p>
      <h2 className="title">A page is a framed document.</h2>
      <p className="section-copy">
        One bordered column, a hairline between sections, a small type ladder. The frame draws its
        side borders down to <code>--frame-w</code> and drops them below 1040px; every section is a
        <code> border-top</code> plus one block step, so the page reads as a document rather than a
        stack of bands. Section headings are 1.375rem; only a landing hero may spend a larger clamp.
      </p>

      <div className="mt-[1.2rem] border border-hair bg-bg">
        <DocumentFrame>
          <div className="px-[var(--page-pad)] py-[var(--page-step)]">
            <PageTitle title="Infrastructure, not a product.">
              A set of parts you assemble, not a platform you move into. Nine modules ship today and
              two more are marked roadmap in the registry rather than quietly counted as built.
            </PageTitle>
          </div>

          <Section
            title="Four properties"
            lede="What the stack guarantees before you write a line of business code."
          >
            <GlyphList>
              {PROPERTIES.map((p) => (
                <GlyphRow key={p.label} label={p.label}>
                  {p.clause}
                </GlyphRow>
              ))}
            </GlyphList>
          </Section>

          <Section title="Prose measure" lede="Reading copy is capped and loosely led.">
            <Prose>
              <p>
                Compatibility is a design goal, not a migration story. The parts are assembled from
                libraries you can name, version and swap, so you can take a piece and leave the
                rest — and nothing in the stack reimplements a database, a scheduler or a model
                runtime it could instead depend on.
              </p>
              <p>
                Where a claim can be counted, it is counted and dated. Where it cannot, it is
                stated as a limit rather than dressed as a feature.
              </p>
            </Prose>
          </Section>
        </DocumentFrame>
      </div>
    </section>
  );
}
