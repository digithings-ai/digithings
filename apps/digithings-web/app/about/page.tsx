import type { Metadata } from "next";
import {
  CtaLink,
  DocumentFrame,
  GlyphList,
  GlyphRow,
  PageTitle,
  Prose,
  Section,
} from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "about — open AI infrastructure you can host",
  description:
    "digithings is a modular, MIT-licensed AI infrastructure repository: self-hostable anywhere, " +
    "bring your own provider keys, every step traceable. Built to compose with the stack you " +
    "already run — not to replace it.",
};

// /about — the positioning page, kept short for clients: four checkable
// properties and the dependencies the code actually imports. How each control
// works, and where it stops, is /security's job; this page links there.

const PROPERTIES: { label: string; body: string }[] = [
  {
    label: "MIT, and public",
    body: "The whole repository — services, tests and CI — is open to read without an account.",
  },
  {
    label: "Self-hostable anywhere",
    body: "One compose file runs the stack on a laptop, a VM or a cluster.",
  },
  {
    label: "Bring your own keys",
    body: "Use any provider LiteLLM speaks. The stack never stores your provider credentials.",
  },
  {
    label: "A glass box",
    body:
      "Every request carries one id through every service, and each step lands in an audit log " +
      "you keep.",
  },
];

const COMPOSES_WITH: { label: string; body: string }[] = [
  { label: "LangGraph", body: "orchestration" },
  { label: "NautilusTrader", body: "backtests and optimisation" },
  { label: "Polars", body: "dataframes" },
  { label: "Pydantic v2", body: "typed models at every boundary" },
  { label: "LiteLLM", body: "provider routing and caching" },
  { label: "MCP", body: "every capability as a discoverable tool" },
  { label: "Docker", body: "one compose file for the whole topology" },
];

export default function AboutPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <DocumentFrame>
          <div className="px-[var(--page-pad)] py-[var(--page-step)]">
            <PageTitle path="about" title="Infrastructure, not a product.">
              digithings is open-source, modular AI infrastructure: parts you run on your own
              hardware with your own keys, instead of a platform you have to move into.
            </PageTitle>
          </div>

          <Section id="properties" title="Four properties" lede="Each one you can check in the repository.">
            <GlyphList>
              {PROPERTIES.map((r) => (
                <GlyphRow key={r.label} label={r.label}>
                  {r.body}
                </GlyphRow>
              ))}
            </GlyphList>
          </Section>

          <Section
            id="compatibility"
            title="Built to compose"
            lede="The tools the code is built on. Take one piece and leave the rest."
          >
            <GlyphList>
              {COMPOSES_WITH.map((r) => (
                <GlyphRow key={r.label} label={r.label}>
                  {r.body}
                </GlyphRow>
              ))}
            </GlyphList>
            <div className="mt-[1.6rem]">
              <Prose>
                <p>
                  Where the stack stops short, it says so. <a href="/security#limits">The security
                  page lists the limits</a>.
                </p>
              </Prose>
            </div>
          </Section>

          <Section id="source" title="Read the source">
            <div className="flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/docs">Read the docs</CtaLink>
              <CtaLink href="https://github.com/digithings-ai/digithings" external variant="ghost">
                Browse the repository
              </CtaLink>
              <CtaLink href="/security#shipping" variant="ghost">
                How it is tested
              </CtaLink>
            </div>
          </Section>
        </DocumentFrame>
      </main>

      <DtFooter />
    </>
  );
}
